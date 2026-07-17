package k8s

import (
	"context"
	"fmt"
	"regexp"

	netv1 "k8s.io/api/networking/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// NetworkGroupLabel marks a user VM as a member of a network isolation group
// (HOP-19 18.3). The namespace default-deny keeps user VMs unable to reach
// each other; VMs sharing this label value get a NetworkPolicy that re-allows
// traffic between them (team projects). The value arrives from the API via
// CreatePodRequest.labels.
const NetworkGroupLabel = "hopper.dev/network-group"

// Group names become K8s label values and NetworkPolicy name suffixes, so
// they must be DNS-label-safe. Max 32 chars keeps "vm-net-group-<g>" well
// under the 63-char object-name limit (the API gateway enforces the same
// shape on input).
var networkGroupRe = regexp.MustCompile(`^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$`)

func ValidNetworkGroup(group string) bool {
	return networkGroupRe.MatchString(group)
}

// EnsureGroupNetworkPolicy idempotently creates the NetworkPolicy that lets
// VMs in `group` reach each other. NetworkPolicies are additive allows, so
// this composes with (rather than replaces) the namespace baseline: the
// default-deny and the pod-CIDR egress exclusion still isolate these VMs
// from every OTHER group and from the platform services.
func (pm *PodManager) EnsureGroupNetworkPolicy(ctx context.Context, group string) error {
	if !ValidNetworkGroup(group) {
		return fmt.Errorf("invalid network group %q", group)
	}
	// role=user-vm is included so a (hypothetical) platform pod carrying a
	// forged group label never becomes reachable from user VMs.
	selector := metav1.LabelSelector{MatchLabels: map[string]string{
		"role":            "user-vm",
		NetworkGroupLabel: group,
	}}
	peer := netv1.NetworkPolicyPeer{PodSelector: &selector}
	policy := &netv1.NetworkPolicy{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("vm-net-group-%s", group),
			Namespace: pm.namespace,
			Labels: map[string]string{
				"app":             "hopper-vm",
				NetworkGroupLabel: group,
			},
		},
		Spec: netv1.NetworkPolicySpec{
			PodSelector: selector,
			PolicyTypes: []netv1.PolicyType{netv1.PolicyTypeIngress, netv1.PolicyTypeEgress},
			Ingress: []netv1.NetworkPolicyIngressRule{
				{From: []netv1.NetworkPolicyPeer{peer}},
			},
			Egress: []netv1.NetworkPolicyEgressRule{
				{To: []netv1.NetworkPolicyPeer{peer}},
			},
		},
	}
	_, err := pm.client.NetworkingV1().NetworkPolicies(pm.namespace).Create(ctx, policy, metav1.CreateOptions{})
	if apierrors.IsAlreadyExists(err) {
		return nil
	}
	return err
}
