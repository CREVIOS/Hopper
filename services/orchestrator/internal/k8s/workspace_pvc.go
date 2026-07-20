package k8s

import (
	"context"
	"fmt"
	"log"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
)

// EnsureWorkspacePVC creates the workspace PVC if absent, and — when it already
// exists and the requested size is larger — expands it in place (FR-HC-30).
//
// Expansion happens ONLY when the PVC's StorageClass has
// allowVolumeExpansion=true (Longhorn does; the local-path provisioner does
// not). If the class can't expand, is unknown, or any get/patch fails (e.g. the
// orchestrator ServiceAccount lacks the RBAC), it logs and continues at the
// current size rather than failing the launch. It NEVER shrinks — block volumes
// can't, and shrinking would risk data loss.
func (pm *PodManager) EnsureWorkspacePVC(
	ctx context.Context, name string, sizeGi int, storageClass string, labels map[string]string,
) error {
	want := resource.MustParse(fmt.Sprintf("%dGi", sizeGi))
	pvc := &corev1.PersistentVolumeClaim{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: pm.namespace, Labels: labels},
		Spec: corev1.PersistentVolumeClaimSpec{
			AccessModes: []corev1.PersistentVolumeAccessMode{corev1.ReadWriteOnce},
			Resources: corev1.VolumeResourceRequirements{
				Requests: corev1.ResourceList{corev1.ResourceStorage: want},
			},
		},
	}
	if storageClass != "" {
		pvc.Spec.StorageClassName = &storageClass
	}
	pvcs := pm.client.CoreV1().PersistentVolumeClaims(pm.namespace)

	// Create: a fresh workspace is provisioned at the requested size.
	_, err := pvcs.Create(ctx, pvc, metav1.CreateOptions{})
	if err == nil {
		return nil
	}
	if !apierrors.IsAlreadyExists(err) {
		return fmt.Errorf("ensuring workspace pvc: %w", err)
	}

	// A returning user already has their PVC — reuse it, expanding only upward.
	existing, err := pvcs.Get(ctx, name, metav1.GetOptions{})
	if err != nil {
		log.Printf("workspace pvc %s: reuse without resize (get failed: %v)", name, err)
		return nil
	}
	cur := existing.Spec.Resources.Requests[corev1.ResourceStorage]
	if want.Cmp(cur) <= 0 {
		return nil // equal or (defensively) smaller — never shrink
	}
	if !pm.storageClassAllowsExpansion(ctx, existing.Spec.StorageClassName) {
		log.Printf(
			"workspace pvc %s: cannot expand %s -> %s (storage class does not allow expansion); keeping current size",
			name, cur.String(), want.String(),
		)
		return nil
	}
	patch := []byte(fmt.Sprintf(`{"spec":{"resources":{"requests":{"storage":"%dGi"}}}}`, sizeGi))
	if _, err := pvcs.Patch(ctx, name, types.MergePatchType, patch, metav1.PatchOptions{}); err != nil {
		log.Printf("workspace pvc %s: expand patch failed (%v); keeping current size", name, err)
		return nil
	}
	log.Printf("workspace pvc %s: expanded %s -> %s", name, cur.String(), want.String())
	return nil
}

// storageClassAllowsExpansion reports whether the named StorageClass permits
// online volume expansion. A nil/empty name (cluster default, unknown here) or
// any lookup error is treated as "no" — we never guess and patch blindly.
func (pm *PodManager) storageClassAllowsExpansion(ctx context.Context, scName *string) bool {
	if scName == nil || *scName == "" {
		return false
	}
	sc, err := pm.client.StorageV1().StorageClasses().Get(ctx, *scName, metav1.GetOptions{})
	if err != nil {
		log.Printf("storage class %s lookup failed: %v", *scName, err)
		return false
	}
	return sc.AllowVolumeExpansion != nil && *sc.AllowVolumeExpansion
}
