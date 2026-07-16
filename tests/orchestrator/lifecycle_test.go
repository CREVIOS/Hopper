package orchestrator_test

import (
	"fmt"
	"strings"
	"sync"
	"testing"

	podmanager "github.com/hopper/orchestrator/internal/pod"
)

func createPod(t *testing.T, manager *podmanager.Manager, id string) *podmanager.Pod {
	t.Helper()

	pod, err := manager.Create(podmanager.CreateOpts{
		ID:        id,
		UserID:    "student-1",
		Plan:      "standard",
		Image:     "pytorch:latest",
		CPU:       "4",
		Memory:    "16Gi",
		Namespace: "student-1",
		PodName:   "gpu-" + id,
	})
	if err != nil {
		t.Fatalf("create pod: %v", err)
	}
	return pod
}

func TestPodLifecycleValidTransitions(t *testing.T) {
	manager := podmanager.NewManager()
	pod := createPod(t, manager, "pod-1")

	if pod.State != podmanager.StatePending {
		t.Fatalf("initial state = %q, want %q", pod.State, podmanager.StatePending)
	}

	states := []podmanager.State{
		podmanager.StateCreating,
		podmanager.StateRunning,
		podmanager.StateStopping,
		podmanager.StateTerminated,
	}
	for _, state := range states {
		if err := manager.Transition(pod.ID, state); err != nil {
			t.Fatalf("transition to %q: %v", state, err)
		}
		stored, ok := manager.Get(pod.ID)
		if !ok {
			t.Fatalf("pod disappeared after transition to %q", state)
		}
		if stored.State != state {
			t.Fatalf("state = %q, want %q", stored.State, state)
		}
	}
}

func TestPodLifecycleRejectsInvalidTransition(t *testing.T) {
	manager := podmanager.NewManager()
	pod := createPod(t, manager, "pod-1")

	err := manager.Transition(pod.ID, podmanager.StateRunning)
	if err == nil {
		t.Fatal("pending -> running succeeded, want an invalid-transition error")
	}
	if !strings.Contains(err.Error(), "invalid transition") {
		t.Fatalf("error = %q, want invalid transition", err)
	}
	if pod.State != podmanager.StatePending {
		t.Fatalf("state changed after rejected transition: got %q", pod.State)
	}
}

func TestPodLifecycleRejectsTransitionFromTerminalState(t *testing.T) {
	manager := podmanager.NewManager()
	pod := createPod(t, manager, "pod-1")
	manager.SetState(pod.ID, podmanager.StateTerminated)

	err := manager.Transition(pod.ID, podmanager.StateRunning)
	if err == nil {
		t.Fatal("terminated -> running succeeded")
	}
	if !strings.Contains(err.Error(), "no transitions") {
		t.Fatalf("error = %q, want no transitions", err)
	}
}

func TestPodLifecycleAllowsFailureFromEveryActiveState(t *testing.T) {
	activeStates := []podmanager.State{
		podmanager.StatePending,
		podmanager.StateCreating,
		podmanager.StateRunning,
		podmanager.StateStopping,
	}

	for _, state := range activeStates {
		t.Run(string(state), func(t *testing.T) {
			manager := podmanager.NewManager()
			pod := createPod(t, manager, "pod-1")
			manager.SetState(pod.ID, state)

			if err := manager.Transition(pod.ID, podmanager.StateFailed); err != nil {
				t.Fatalf("%s -> failed: %v", state, err)
			}
			if pod.State != podmanager.StateFailed {
				t.Fatalf("state = %q, want failed", pod.State)
			}
		})
	}
}

func TestPodCreationIsIdempotent(t *testing.T) {
	manager := podmanager.NewManager()
	first := createPod(t, manager, "pod-1")

	second, err := manager.Create(podmanager.CreateOpts{
		ID:     first.ID,
		UserID: "different-user",
		Plan:   "different-plan",
	})
	if err != nil {
		t.Fatalf("second create: %v", err)
	}
	if second != first {
		t.Fatal("duplicate creation returned a different pod")
	}
	if second.UserID != "student-1" || second.Plan != "standard" {
		t.Fatalf("duplicate creation mutated pod: %+v", second)
	}
}

func TestConcurrentPodCreationIsIdempotent(t *testing.T) {
	manager := podmanager.NewManager()
	const goroutines = 32

	results := make(chan *podmanager.Pod, goroutines)
	errors := make(chan error, goroutines)
	var wg sync.WaitGroup
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			pod, err := manager.Create(podmanager.CreateOpts{
				ID:     "shared-pod",
				UserID: fmt.Sprintf("student-%d", index),
			})
			if err != nil {
				errors <- err
				return
			}
			results <- pod
		}(i)
	}
	wg.Wait()
	close(results)
	close(errors)

	for err := range errors {
		t.Errorf("concurrent create: %v", err)
	}

	var first *podmanager.Pod
	count := 0
	for result := range results {
		count++
		if first == nil {
			first = result
		}
		if result != first {
			t.Error("concurrent creates returned different pod instances")
		}
	}
	if count != goroutines {
		t.Fatalf("received %d results, want %d", count, goroutines)
	}
}

func TestTransitionOfUnknownPodFails(t *testing.T) {
	manager := podmanager.NewManager()

	err := manager.Transition("missing", podmanager.StateCreating)
	if err == nil || !strings.Contains(err.Error(), "not found") {
		t.Fatalf("error = %v, want pod-not-found error", err)
	}
}

func TestListRunningReturnsOnlyRunningPods(t *testing.T) {
	manager := podmanager.NewManager()
	running := createPod(t, manager, "running")
	createPod(t, manager, "pending")
	failed := createPod(t, manager, "failed")
	manager.SetState(running.ID, podmanager.StateRunning)
	manager.SetState(failed.ID, podmanager.StateFailed)

	pods := manager.ListRunning()
	if len(pods) != 1 || pods[0].ID != running.ID {
		t.Fatalf("running pods = %+v, want only %q", pods, running.ID)
	}
}

func TestConnectionDetailsAreStored(t *testing.T) {
	manager := podmanager.NewManager()
	pod := createPod(t, manager, "pod-1")

	manager.SetPorts(pod.ID, 30022, 30080)
	manager.SetSshPassword(pod.ID, "generated-secret")

	stored, ok := manager.Get(pod.ID)
	if !ok {
		t.Fatal("pod not found")
	}
	if stored.SshPort != 30022 || stored.VSCodePort != 30080 {
		t.Fatalf("ports = (%d, %d), want (30022, 30080)", stored.SshPort, stored.VSCodePort)
	}
	if stored.SshPassword != "generated-secret" {
		t.Fatalf("SSH password = %q", stored.SshPassword)
	}
}
