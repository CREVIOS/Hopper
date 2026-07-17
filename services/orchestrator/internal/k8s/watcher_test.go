package k8s

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
	"go.uber.org/zap"

	"github.com/hopper/orchestrator/internal/billing"
	"github.com/hopper/orchestrator/internal/pod"
)

func TestObservePhasePublishesOnlyOnPendingToRunningTransition(t *testing.T) {
	var published []string
	w := NewPodWatcher(
		fake.NewSimpleClientset(),
		"hopper",
		zap.NewNop(),
		func(subject string, data any) error {
			published = append(published, subject)
			return nil
		},
	)

	p := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name: "vm-1",
			Labels: map[string]string{
				"hopper.dev/pod-id":  "pod-1",
				"hopper.dev/user-id": "user-1",
			},
		},
		Status: corev1.PodStatus{Phase: corev1.PodPending},
	}
	w.observePhase(p)
	if len(published) != 0 {
		t.Fatalf("unexpected publish on first pending observation: %v", published)
	}

	p.Status.Phase = corev1.PodRunning
	w.observePhase(p)
	if len(published) != 1 || published[0] != "pod.started" {
		t.Fatalf("published = %v, want one pod.started", published)
	}

	w.observePhase(p)
	if len(published) != 1 {
		t.Fatalf("duplicate running observation republished: %v", published)
	}
}

func TestObservePhaseSkipsRunningPodsWithoutLabels(t *testing.T) {
	var published []string
	w := NewPodWatcher(
		fake.NewSimpleClientset(),
		"hopper",
		zap.NewNop(),
		func(subject string, data any) error {
			published = append(published, subject)
			return nil
		},
	)

	w.lastPhase["vm-1"] = corev1.PodPending
	w.observePhase(&corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "vm-1"},
		Status:     corev1.PodStatus{Phase: corev1.PodRunning},
	})

	if len(published) != 0 {
		t.Fatalf("published = %v, want none", published)
	}
}

func TestReconcileRestoresManagedPodStatePortsAndPassword(t *testing.T) {
	client := fake.NewSimpleClientset(
		&corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "vm-1",
				Namespace: "hopper",
				Labels: map[string]string{
					"app":                "hopper-vm",
					"hopper.dev/pod-id":  "pod-1",
					"hopper.dev/user-id": "user-1",
					"hopper.dev/plan":    "small",
				},
				Annotations: map[string]string{
					SshPasswordAnnotation: "secret",
				},
			},
			Spec: corev1.PodSpec{
				Containers: []corev1.Container{{
					Image: "hopper/vm-ubuntu:22.04",
					Resources: corev1.ResourceRequirements{
						Limits: corev1.ResourceList{
							corev1.ResourceCPU:    resource.MustParse("1"),
							corev1.ResourceMemory: resource.MustParse("2Gi"),
						},
					},
				}},
			},
			Status: corev1.PodStatus{Phase: corev1.PodRunning},
		},
		&corev1.Service{
			ObjectMeta: metav1.ObjectMeta{Name: "ssh-vm-1", Namespace: "hopper"},
			Spec: corev1.ServiceSpec{Ports: []corev1.ServicePort{
				{Name: "ssh", NodePort: 30022},
				{Name: "vscode", NodePort: 30080},
			}},
		},
	)
	manager := pod.NewManager()
	ticker := billing.NewTicker(zap.NewNop())
	w := NewPodWatcher(client, "hopper", zap.NewNop(), func(string, any) error { return nil })

	w.Reconcile(context.Background(), manager, ticker)

	got, ok := manager.Get("pod-1")
	if !ok {
		t.Fatal("reconciled pod not found")
	}
	if got.State != pod.StateRunning {
		t.Fatalf("state = %q", got.State)
	}
	if got.SshPort != 30022 || got.VSCodePort != 30080 {
		t.Fatalf("ports = %d/%d", got.SshPort, got.VSCodePort)
	}
	if got.SshPassword != "secret" {
		t.Fatalf("ssh password = %q", got.SshPassword)
	}
}

func TestK8sPhaseToStateMappings(t *testing.T) {
	cases := map[corev1.PodPhase]pod.State{
		corev1.PodPending:   pod.StateCreating,
		corev1.PodRunning:   pod.StateRunning,
		corev1.PodSucceeded: pod.StateTerminated,
		corev1.PodFailed:    pod.StateFailed,
		"":                  pod.StatePending,
	}
	for phase, want := range cases {
		if got := k8sPhaseToState(phase); got != want {
			t.Fatalf("phase %q => %q, want %q", phase, got, want)
		}
	}
}
