package k8s

import (
	"context"
	"sync"
	"testing"
	"time"

	"go.uber.org/zap"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"

	"github.com/hopper/orchestrator/internal/pod"
)

func TestUnschedulableReason(t *testing.T) {
	now := time.Now()
	old := metav1.NewTime(now.Add(-5 * time.Minute))
	recent := metav1.NewTime(now.Add(-10 * time.Second))
	maxPending := 2 * time.Minute

	unschedulable := []corev1.PodCondition{{
		Type:    corev1.PodScheduled,
		Status:  corev1.ConditionFalse,
		Reason:  "Unschedulable",
		Message: "0/3 nodes are available: 2 Insufficient memory.",
	}}

	cases := []struct {
		name     string
		pod      *corev1.Pod
		wantReap bool
	}{
		{
			name: "old and unschedulable is reaped",
			pod: &corev1.Pod{
				ObjectMeta: metav1.ObjectMeta{CreationTimestamp: old},
				Status:     corev1.PodStatus{Phase: corev1.PodPending, Conditions: unschedulable},
			},
			wantReap: true,
		},
		{
			name: "recently created is spared even if unschedulable",
			pod: &corev1.Pod{
				ObjectMeta: metav1.ObjectMeta{CreationTimestamp: recent},
				Status:     corev1.PodStatus{Phase: corev1.PodPending, Conditions: unschedulable},
			},
			wantReap: false,
		},
		{
			name: "running is never reaped",
			pod: &corev1.Pod{
				ObjectMeta: metav1.ObjectMeta{CreationTimestamp: old},
				Status:     corev1.PodStatus{Phase: corev1.PodRunning},
			},
			wantReap: false,
		},
		{
			name: "pending for a non-scheduling reason is spared",
			pod: &corev1.Pod{
				ObjectMeta: metav1.ObjectMeta{CreationTimestamp: old},
				Status: corev1.PodStatus{Phase: corev1.PodPending, Conditions: []corev1.PodCondition{{
					Type: corev1.PodScheduled, Status: corev1.ConditionTrue,
				}}},
			},
			wantReap: false,
		},
		{
			name: "pending with no conditions is spared",
			pod: &corev1.Pod{
				ObjectMeta: metav1.ObjectMeta{CreationTimestamp: old},
				Status:     corev1.PodStatus{Phase: corev1.PodPending},
			},
			wantReap: false,
		},
	}

	for _, c := range cases {
		got := unschedulableReason(c.pod, now, maxPending)
		if (got != "") != c.wantReap {
			t.Errorf("%s: reason=%q, wantReap=%v", c.name, got, c.wantReap)
		}
	}
}

// TestReapUnschedulableOnce covers the reap ordering the reviewer flagged as
// untested: an old, unschedulable Pending VM is deleted, its managed state is
// set Terminated BEFORE the delete (so the watch loop treats the delete as
// intentional and does not double-publish pod.stopped), and a pod.failed event
// with notify=true reaches the gateway.
func TestReapUnschedulableOnce(t *testing.T) {
	old := metav1.NewTime(time.Now().Add(-5 * time.Minute))
	stuck := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:              "vm-stuck",
			Namespace:         "hopper",
			CreationTimestamp: old,
			Labels: map[string]string{
				"app":                "hopper-vm",
				"hopper.dev/pod-id":  "pid-1",
				"hopper.dev/user-id": "u-1",
			},
		},
		Status: corev1.PodStatus{
			Phase: corev1.PodPending,
			Conditions: []corev1.PodCondition{{
				Type: corev1.PodScheduled, Status: corev1.ConditionFalse,
				Reason: "Unschedulable", Message: "0/2 nodes are available: Insufficient memory.",
			}},
		},
	}
	// A healthy running VM that must be left completely alone.
	healthy := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name: "vm-ok", Namespace: "hopper", CreationTimestamp: old,
			Labels: map[string]string{"app": "hopper-vm", "hopper.dev/pod-id": "pid-2"},
		},
		Status: corev1.PodStatus{Phase: corev1.PodRunning},
	}
	client := fake.NewSimpleClientset(stuck, healthy)

	var mu sync.Mutex
	var events []map[string]string
	publish := func(subject string, data any) error {
		if subject != "pod.failed" {
			return nil
		}
		mu.Lock()
		defer mu.Unlock()
		if m, ok := data.(map[string]string); ok {
			events = append(events, m)
		}
		return nil
	}

	w := NewPodWatcher(client, "hopper", zap.NewNop(), publish)
	podMgr := pod.NewManager()
	if _, err := podMgr.Create(pod.CreateOpts{
		ID: "vm-stuck", UserID: "u-1", Plan: "large", Namespace: "hopper", PodName: "vm-stuck",
	}); err != nil {
		t.Fatalf("registering managed pod: %v", err)
	}
	pm := NewPodManager(client, "hopper")

	reaped := w.reapUnschedulableOnce(context.Background(), podMgr, pm, 2*time.Minute)
	if reaped != 1 {
		t.Fatalf("reaped = %d, want 1", reaped)
	}

	// The managed pod was marked Terminated (before delete), so the watch loop's
	// Deleted handler will suppress a duplicate pod.stopped.
	if mgd, ok := podMgr.GetByPodName("vm-stuck"); !ok || mgd.State != pod.StateTerminated {
		t.Errorf("managed state = %v (ok=%v), want Terminated", mgd, ok)
	}

	// The stuck pod is gone; the healthy one remains.
	if _, err := client.CoreV1().Pods("hopper").Get(context.Background(), "vm-stuck", metav1.GetOptions{}); err == nil {
		t.Errorf("stuck pod still exists, expected deleted")
	}
	if _, err := client.CoreV1().Pods("hopper").Get(context.Background(), "vm-ok", metav1.GetOptions{}); err != nil {
		t.Errorf("healthy pod was deleted: %v", err)
	}

	// Exactly one pod.failed{notify:true, reason:unschedulable} for the stuck VM.
	if len(events) != 1 {
		t.Fatalf("pod.failed events = %d, want 1", len(events))
	}
	ev := events[0]
	if ev["notify"] != "true" || ev["reason"] != "unschedulable" || ev["user_id"] != "u-1" {
		t.Errorf("pod.failed payload = %v, want notify=true reason=unschedulable user_id=u-1", ev)
	}
}
