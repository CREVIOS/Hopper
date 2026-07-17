package k8s

import (
	"context"
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func TestValidNetworkGroup(t *testing.T) {
	valid := []string{"cse101", "team-1", "a", "a1-b2-c3", "x0"}
	for _, g := range valid {
		if !ValidNetworkGroup(g) {
			t.Errorf("ValidNetworkGroup(%q) = false, want true", g)
		}
	}
	invalid := []string{"", "-lead", "trail-", "UPPER", "has_underscore", "has.dot",
		"this-name-is-far-too-long-for-a-network-group"}
	for _, g := range invalid {
		if ValidNetworkGroup(g) {
			t.Errorf("ValidNetworkGroup(%q) = true, want false", g)
		}
	}
}

func TestEnsureGroupNetworkPolicyCreatesAndIsIdempotent(t *testing.T) {
	client := fake.NewSimpleClientset()
	pm := NewPodManager(client, "hopper")
	ctx := context.Background()

	if err := pm.EnsureGroupNetworkPolicy(ctx, "cse101-team1"); err != nil {
		t.Fatalf("first ensure: %v", err)
	}
	// Second call must tolerate AlreadyExists.
	if err := pm.EnsureGroupNetworkPolicy(ctx, "cse101-team1"); err != nil {
		t.Fatalf("second ensure: %v", err)
	}

	pol, err := client.NetworkingV1().NetworkPolicies("hopper").Get(
		ctx, "vm-net-group-cse101-team1", metav1.GetOptions{})
	if err != nil {
		t.Fatalf("policy not created: %v", err)
	}

	sel := pol.Spec.PodSelector.MatchLabels
	if sel[NetworkGroupLabel] != "cse101-team1" || sel["role"] != "user-vm" {
		t.Errorf("pod selector = %v, want role=user-vm + group label", sel)
	}
	if len(pol.Spec.Ingress) != 1 || len(pol.Spec.Egress) != 1 {
		t.Fatalf("want 1 ingress + 1 egress rule, got %d/%d",
			len(pol.Spec.Ingress), len(pol.Spec.Egress))
	}
	// Both rules must point ONLY at same-group peers — never a wider allow.
	in := pol.Spec.Ingress[0].From
	out := pol.Spec.Egress[0].To
	if len(in) != 1 || in[0].PodSelector.MatchLabels[NetworkGroupLabel] != "cse101-team1" {
		t.Errorf("ingress peer = %+v, want same-group pod selector", in)
	}
	if len(out) != 1 || out[0].PodSelector.MatchLabels[NetworkGroupLabel] != "cse101-team1" {
		t.Errorf("egress peer = %+v, want same-group pod selector", out)
	}
	if in[0].IPBlock != nil || out[0].IPBlock != nil || in[0].NamespaceSelector != nil {
		t.Error("peers must be pod-selector-only (no ipBlock/namespaceSelector)")
	}
}

func TestEnsureGroupNetworkPolicyRejectsInvalidGroup(t *testing.T) {
	pm := NewPodManager(fake.NewSimpleClientset(), "hopper")
	if err := pm.EnsureGroupNetworkPolicy(context.Background(), "Bad_Group"); err == nil {
		t.Fatal("want error for invalid group name")
	}
}

func TestCreatePodAppliesNetworkGroupLabelAndPolicy(t *testing.T) {
	client := fake.NewSimpleClientset()
	pm := NewPodManager(client, "hopper")
	ctx := context.Background()

	_, err := pm.CreatePod(ctx, CreatePodOpts{
		PodName: "vm-123", PodID: "pod-uuid", UserID: "u1", Plan: "small",
		Image: "hopper/vm-ubuntu:22.04", CPU: "1", Memory: "2Gi",
		NetworkGroup: "cse101",
	})
	if err != nil {
		t.Fatalf("CreatePod: %v", err)
	}

	pod, err := client.CoreV1().Pods("hopper").Get(ctx, "vm-123", metav1.GetOptions{})
	if err != nil {
		t.Fatalf("pod not created: %v", err)
	}
	if pod.Labels[NetworkGroupLabel] != "cse101" {
		t.Errorf("pod label %s = %q, want cse101", NetworkGroupLabel, pod.Labels[NetworkGroupLabel])
	}
	if _, err := client.NetworkingV1().NetworkPolicies("hopper").Get(
		ctx, "vm-net-group-cse101", metav1.GetOptions{}); err != nil {
		t.Errorf("group policy not ensured: %v", err)
	}

	// No group → no label, no stray policy.
	_, err = pm.CreatePod(ctx, CreatePodOpts{
		PodName: "vm-456", PodID: "pod-uuid-2", UserID: "u2", Plan: "small",
		Image: "hopper/vm-ubuntu:22.04", CPU: "1", Memory: "2Gi",
	})
	if err != nil {
		t.Fatalf("CreatePod (ungrouped): %v", err)
	}
	pod2, _ := client.CoreV1().Pods("hopper").Get(ctx, "vm-456", metav1.GetOptions{})
	if _, ok := pod2.Labels[NetworkGroupLabel]; ok {
		t.Error("ungrouped pod must not carry the network-group label")
	}
	policies, _ := client.NetworkingV1().NetworkPolicies("hopper").List(ctx, metav1.ListOptions{})
	if len(policies.Items) != 1 {
		t.Errorf("want exactly 1 policy, got %d", len(policies.Items))
	}
}
