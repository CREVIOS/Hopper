package k8s

import (
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// vmReady builds a node spec that carries the vm-ready label, so a case only
// tests the taint/cordon dimension it names rather than also tripping the
// label gate.
func vmReady(spec corev1.NodeSpec) *corev1.Node {
	return &corev1.Node{
		ObjectMeta: metav1.ObjectMeta{Labels: map[string]string{VMReadyLabel: VMReadyValue}},
		Spec:       spec,
	}
}

func TestSchedulableForVMs(t *testing.T) {
	cases := []struct {
		name string
		node *corev1.Node
		want bool
	}{
		{"prepared worker", vmReady(corev1.NodeSpec{}), true},
		{"cordoned", vmReady(corev1.NodeSpec{Unschedulable: true}), false},
		{"control-plane NoSchedule taint", vmReady(corev1.NodeSpec{
			Taints: []corev1.Taint{{Key: "node-role.kubernetes.io/control-plane", Effect: corev1.TaintEffectNoSchedule}},
		}), false},
		{"NoExecute taint", vmReady(corev1.NodeSpec{
			Taints: []corev1.Taint{{Key: "x", Effect: corev1.TaintEffectNoExecute}},
		}), false},
		{"PreferNoSchedule is still schedulable", vmReady(corev1.NodeSpec{
			Taints: []corev1.Taint{{Key: "x", Effect: corev1.TaintEffectPreferNoSchedule}},
		}), true},
		// The vm-ready gate: an unprepared node (freshly joined, no lxcfs / no VM
		// images) must be refused even though it is otherwise schedulable.
		{"no vm-ready label", &corev1.Node{}, false},
		{"vm-ready label wrong value", &corev1.Node{
			ObjectMeta: metav1.ObjectMeta{Labels: map[string]string{VMReadyLabel: "false"}},
		}, false},
	}
	for _, c := range cases {
		if got := schedulableForVMs(c.node); got != c.want {
			t.Errorf("%s: schedulableForVMs = %v, want %v", c.name, got, c.want)
		}
	}
}
