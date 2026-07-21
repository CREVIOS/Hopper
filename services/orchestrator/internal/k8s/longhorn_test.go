package k8s

import (
	"context"
	"fmt"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	dynamicfake "k8s.io/client-go/dynamic/fake"
	kfake "k8s.io/client-go/kubernetes/fake"
)

func lhNode(name string, disks ...map[string]interface{}) *unstructured.Unstructured {
	ds := map[string]interface{}{}
	for i, d := range disks {
		ds[fmt.Sprintf("disk-%d", i)] = d
	}
	return &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "longhorn.io/v1beta2",
		"kind":       "Node",
		"metadata":   map[string]interface{}{"name": name, "namespace": "longhorn-system"},
		"status":     map[string]interface{}{"diskStatus": ds},
	}}
}

func newLonghornFake(objs ...runtime.Object) *dynamicfake.FakeDynamicClient {
	scheme := runtime.NewScheme()
	gvrToListKind := map[schema.GroupVersionResource]string{longhornNodeGVR: "NodeList"}
	return dynamicfake.NewSimpleDynamicClientWithCustomListKinds(scheme, gvrToListKind, objs...)
}

func TestLonghornReader_NodeStorage_SumsDisks(t *testing.T) {
	n1 := lhNode("node-1",
		map[string]interface{}{"storageMaximum": int64(100), "storageAvailable": int64(80), "storageScheduled": int64(20)},
		map[string]interface{}{"storageMaximum": int64(50), "storageAvailable": int64(50), "storageScheduled": int64(0)},
	)
	nEmpty := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "longhorn.io/v1beta2", "kind": "Node",
		"metadata": map[string]interface{}{"name": "node-2", "namespace": "longhorn-system"},
	}} // no status → contributes zeros
	r := NewLonghornReader(newLonghornFake(n1, nEmpty), "longhorn-system")

	got, err := r.NodeStorage(context.Background())
	if err != nil {
		t.Fatalf("NodeStorage: %v", err)
	}
	if s := got["node-1"]; s.CapacityBytes != 150 || s.AvailableBytes != 130 || s.ScheduledBytes != 20 {
		t.Errorf("node-1 = %+v, want {150 130 20}", s)
	}
	if s := got["node-2"]; s != (NodeStorage{}) {
		t.Errorf("node-2 (no status) = %+v, want zeros", s)
	}
}

func TestListNodes_EnrichedWithLonghornStorage(t *testing.T) {
	node := &corev1.Node{
		ObjectMeta: metav1.ObjectMeta{Name: "node-1"},
		Status: corev1.NodeStatus{
			Conditions: []corev1.NodeCondition{{Type: corev1.NodeReady, Status: corev1.ConditionTrue}},
		},
	}
	pm := NewPodManager(kfake.NewSimpleClientset(node), "hopper")
	pm.SetLonghornReader(NewLonghornReader(newLonghornFake(
		lhNode("node-1", map[string]interface{}{
			"storageMaximum": int64(256), "storageAvailable": int64(200), "storageScheduled": int64(56),
		}),
	), "longhorn-system"))

	nodes, err := pm.ListNodes(context.Background())
	if err != nil {
		t.Fatalf("ListNodes: %v", err)
	}
	if len(nodes) != 1 {
		t.Fatalf("got %d nodes, want 1", len(nodes))
	}
	if nodes[0].StorageCapacityBytes != 256 || nodes[0].StorageAvailableBytes != 200 || nodes[0].StorageScheduledBytes != 56 {
		t.Errorf("node storage = %d/%d/%d, want 256/200/56",
			nodes[0].StorageCapacityBytes, nodes[0].StorageAvailableBytes, nodes[0].StorageScheduledBytes)
	}
}

func TestListNodes_NoLonghornReaderLeavesZeros(t *testing.T) {
	node := &corev1.Node{
		ObjectMeta: metav1.ObjectMeta{Name: "node-1"},
		Status: corev1.NodeStatus{
			Conditions: []corev1.NodeCondition{{Type: corev1.NodeReady, Status: corev1.ConditionTrue}},
		},
	}
	pm := NewPodManager(kfake.NewSimpleClientset(node), "hopper") // no reader wired
	nodes, err := pm.ListNodes(context.Background())
	if err != nil {
		t.Fatalf("ListNodes: %v", err)
	}
	if nodes[0].StorageCapacityBytes != 0 {
		t.Errorf("storage = %d, want 0 when Longhorn absent", nodes[0].StorageCapacityBytes)
	}
}
