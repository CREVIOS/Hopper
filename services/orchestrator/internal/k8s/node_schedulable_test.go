package k8s

import (
	"testing"

	corev1 "k8s.io/api/core/v1"
)

func TestSchedulableForVMs(t *testing.T) {
	cases := []struct {
		name string
		node *corev1.Node
		want bool
	}{
		{"plain worker", &corev1.Node{}, true},
		{"cordoned", &corev1.Node{Spec: corev1.NodeSpec{Unschedulable: true}}, false},
		{"control-plane NoSchedule taint", &corev1.Node{Spec: corev1.NodeSpec{
			Taints: []corev1.Taint{{Key: "node-role.kubernetes.io/control-plane", Effect: corev1.TaintEffectNoSchedule}},
		}}, false},
		{"NoExecute taint", &corev1.Node{Spec: corev1.NodeSpec{
			Taints: []corev1.Taint{{Key: "x", Effect: corev1.TaintEffectNoExecute}},
		}}, false},
		{"PreferNoSchedule is still schedulable", &corev1.Node{Spec: corev1.NodeSpec{
			Taints: []corev1.Taint{{Key: "x", Effect: corev1.TaintEffectPreferNoSchedule}},
		}}, true},
	}
	for _, c := range cases {
		if got := schedulableForVMs(c.node); got != c.want {
			t.Errorf("%s: schedulableForVMs = %v, want %v", c.name, got, c.want)
		}
	}
}
