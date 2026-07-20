package k8s

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	storagev1 "k8s.io/api/storage/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func boolPtr(b bool) *bool { return &b }

func existingPVC(name, size, sc string) *corev1.PersistentVolumeClaim {
	return &corev1.PersistentVolumeClaim{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: "hopper"},
		Spec: corev1.PersistentVolumeClaimSpec{
			AccessModes:      []corev1.PersistentVolumeAccessMode{corev1.ReadWriteOnce},
			StorageClassName: &sc,
			Resources: corev1.VolumeResourceRequirements{
				Requests: corev1.ResourceList{corev1.ResourceStorage: resource.MustParse(size)},
			},
		},
	}
}

func storageClass(name string, expand bool) *storagev1.StorageClass {
	return &storagev1.StorageClass{
		ObjectMeta:           metav1.ObjectMeta{Name: name},
		AllowVolumeExpansion: boolPtr(expand),
	}
}

func pvcStorage(t *testing.T, client *fake.Clientset, name string) string {
	t.Helper()
	got, err := client.CoreV1().PersistentVolumeClaims("hopper").Get(context.Background(), name, metav1.GetOptions{})
	if err != nil {
		t.Fatalf("get pvc %s: %v", name, err)
	}
	q := got.Spec.Resources.Requests[corev1.ResourceStorage]
	return q.String()
}

func TestEnsureWorkspacePVC_CreatesWhenAbsent(t *testing.T) {
	client := fake.NewSimpleClientset()
	pm := NewPodManager(client, "hopper")
	if err := pm.EnsureWorkspacePVC(context.Background(), "ws-user-a", 20, "longhorn-workspace", map[string]string{"app": "x"}); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := pvcStorage(t, client, "ws-user-a"); got != "20Gi" {
		t.Errorf("created size = %s, want 20Gi", got)
	}
}

func TestEnsureWorkspacePVC_ExpandsWhenLargerAndAllowed(t *testing.T) {
	client := fake.NewSimpleClientset(
		existingPVC("ws-user-a", "20Gi", "longhorn-workspace"),
		storageClass("longhorn-workspace", true),
	)
	pm := NewPodManager(client, "hopper")
	if err := pm.EnsureWorkspacePVC(context.Background(), "ws-user-a", 50, "longhorn-workspace", nil); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := pvcStorage(t, client, "ws-user-a"); got != "50Gi" {
		t.Errorf("expanded size = %s, want 50Gi", got)
	}
}

func TestEnsureWorkspacePVC_SkipsExpandWhenClassForbids(t *testing.T) {
	client := fake.NewSimpleClientset(
		existingPVC("ws-user-a", "20Gi", "local-path"),
		storageClass("local-path", false),
	)
	pm := NewPodManager(client, "hopper")
	if err := pm.EnsureWorkspacePVC(context.Background(), "ws-user-a", 50, "local-path", nil); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := pvcStorage(t, client, "ws-user-a"); got != "20Gi" {
		t.Errorf("size = %s, want unchanged 20Gi (local-path can't expand)", got)
	}
}

func TestEnsureWorkspacePVC_NeverShrinks(t *testing.T) {
	client := fake.NewSimpleClientset(
		existingPVC("ws-user-a", "100Gi", "longhorn-workspace"),
		storageClass("longhorn-workspace", true),
	)
	pm := NewPodManager(client, "hopper")
	if err := pm.EnsureWorkspacePVC(context.Background(), "ws-user-a", 20, "longhorn-workspace", nil); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := pvcStorage(t, client, "ws-user-a"); got != "100Gi" {
		t.Errorf("size = %s, want unchanged 100Gi (never shrink)", got)
	}
}

func TestEnsureWorkspacePVC_SkipsExpandWhenClassMissing(t *testing.T) {
	// PVC exists but its StorageClass object can't be found → cannot confirm
	// expansion is allowed → keep current size, no error (launch proceeds).
	client := fake.NewSimpleClientset(existingPVC("ws-user-a", "20Gi", "ghost-sc"))
	pm := NewPodManager(client, "hopper")
	if err := pm.EnsureWorkspacePVC(context.Background(), "ws-user-a", 50, "ghost-sc", nil); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := pvcStorage(t, client, "ws-user-a"); got != "20Gi" {
		t.Errorf("size = %s, want unchanged 20Gi (SC unknown)", got)
	}
}
