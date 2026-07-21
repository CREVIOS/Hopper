package k8s

import (
	"context"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
)

// longhornNodeGVR is the Longhorn Node custom resource (v1.12 ships v1beta2).
// A nodes.longhorn.io object's name equals the Kubernetes node name.
var longhornNodeGVR = schema.GroupVersionResource{
	Group: "longhorn.io", Version: "v1beta2", Resource: "nodes",
}

// NodeStorage is the per-node disk totals Longhorn reports, in bytes.
type NodeStorage struct {
	CapacityBytes  int64
	AvailableBytes int64
	ScheduledBytes int64
}

// LonghornReader reads real per-node storage from the Longhorn Node CRs via a
// dynamic client, so no typed Longhorn dependency is needed. It is entirely
// optional: when Longhorn isn't installed (the CRD is absent) List errors and
// the caller falls back to the configured storage pool.
type LonghornReader struct {
	dyn       dynamic.Interface
	namespace string
}

func NewLonghornReader(dyn dynamic.Interface, namespace string) *LonghornReader {
	if namespace == "" {
		namespace = "longhorn-system"
	}
	return &LonghornReader{dyn: dyn, namespace: namespace}
}

// NodeStorage returns storage totals keyed by Kubernetes node name, summed over
// each Longhorn node's disks (status.diskStatus[*].storage{Maximum,Available,
// Scheduled}). A node CR without a populated status contributes zeros; a List
// error (e.g. Longhorn not installed, or missing RBAC) is returned so the
// caller keeps its configured pool authoritative.
func (r *LonghornReader) NodeStorage(ctx context.Context) (map[string]NodeStorage, error) {
	list, err := r.dyn.Resource(longhornNodeGVR).Namespace(r.namespace).List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, err
	}
	out := make(map[string]NodeStorage, len(list.Items))
	for i := range list.Items {
		item := list.Items[i]
		var ns NodeStorage
		disks, found, _ := unstructured.NestedMap(item.Object, "status", "diskStatus")
		if found {
			for _, d := range disks {
				dm, ok := d.(map[string]interface{})
				if !ok {
					continue
				}
				maxB, _, _ := unstructured.NestedInt64(dm, "storageMaximum")
				availB, _, _ := unstructured.NestedInt64(dm, "storageAvailable")
				schedB, _, _ := unstructured.NestedInt64(dm, "storageScheduled")
				ns.CapacityBytes += maxB
				ns.AvailableBytes += availB
				ns.ScheduledBytes += schedB
			}
		}
		out[item.GetName()] = ns
	}
	return out, nil
}
