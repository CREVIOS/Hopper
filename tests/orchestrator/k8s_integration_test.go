package orchestrator_test

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"

	hopperk8s "github.com/hopper/orchestrator/internal/k8s"
)

func TestCreatePodUsesIsolationAndResourceLimits(t *testing.T) {
	client := fake.NewSimpleClientset()
	manager := hopperk8s.NewPodManager(client, "hopper")
	_, err := manager.CreatePod(context.Background(), hopperk8s.CreatePodOpts{
		PodName: "vm-pod-1", PodID: "pod-1", UserID: "student-1", Plan: "medium",
		Image: "hopper/vm-ubuntu:22.04", CPU: "2", Memory: "4Gi", DiskGiB: 10,
	})
	if err != nil {
		t.Fatalf("create pod: %v", err)
	}
	pod, err := client.CoreV1().Pods("hopper").Get(context.Background(), "vm-pod-1", metav1.GetOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if pod.Spec.AutomountServiceAccountToken == nil || *pod.Spec.AutomountServiceAccountToken {
		t.Fatal("service account token must be disabled")
	}
	container := pod.Spec.Containers[0]
	if container.Resources.Limits.Cpu().String() != "2" || container.Resources.Limits.Memory().String() != "4Gi" {
		t.Fatalf("wrong limits: %v", container.Resources.Limits)
	}
	if container.SecurityContext.AllowPrivilegeEscalation == nil || *container.SecurityContext.AllowPrivilegeEscalation {
		t.Fatal("privilege escalation must be disabled")
	}
	if pod.Labels["hopper.dev/user-id"] != "student-1" {
		t.Fatalf("missing tenant label: %v", pod.Labels)
	}
	if _, err := client.CoreV1().PersistentVolumeClaims("hopper").Get(context.Background(), "ws-vm-pod-1", metav1.GetOptions{}); err != nil {
		t.Fatal("workspace PVC missing")
	}
}

func TestDeletePodCleansPodServiceAndWorkspace(t *testing.T) {
	client := fake.NewSimpleClientset(
		&corev1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "vm-pod-1", Namespace: "hopper"}},
		&corev1.Service{ObjectMeta: metav1.ObjectMeta{Name: "ssh-vm-pod-1", Namespace: "hopper"}},
		&corev1.PersistentVolumeClaim{ObjectMeta: metav1.ObjectMeta{Name: "ws-vm-pod-1", Namespace: "hopper"}},
	)
	manager := hopperk8s.NewPodManager(client, "hopper")
	if err := manager.DeletePod(context.Background(), "vm-pod-1"); err != nil {
		t.Fatal(err)
	}
	if pods, _ := client.CoreV1().Pods("hopper").List(context.Background(), metav1.ListOptions{}); len(pods.Items) != 0 {
		t.Fatal("pod not deleted")
	}
	if services, _ := client.CoreV1().Services("hopper").List(context.Background(), metav1.ListOptions{}); len(services.Items) != 0 {
		t.Fatal("service not deleted")
	}
	if pvcs, _ := client.CoreV1().PersistentVolumeClaims("hopper").List(context.Background(), metav1.ListOptions{}); len(pvcs.Items) != 0 {
		t.Fatal("PVC not deleted")
	}
}
