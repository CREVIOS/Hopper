package k8s

import (
	"context"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"
	"k8s.io/client-go/kubernetes"
)

type PodManager struct {
	client    *kubernetes.Clientset
	namespace string
}

func NewPodManager(client *kubernetes.Clientset, namespace string) *PodManager {
	return &PodManager{client: client, namespace: namespace}
}

type CreatePodOpts struct {
	PodName string
	PodID   string
	UserID  string
	Plan    string
	Image   string
	CPU     string
	Memory  string
}



type PodPorts struct{
	SSHPort int32
	VSCodePort int32
}

// CreatePod creates a K8s Pod with resource limits and a NodePort Service for SSH.
// Returns the assigned SSH NodePort.
func (pm *PodManager) CreatePod(ctx context.Context, opts CreatePodOpts) (PodPorts, error) {
	labels := map[string]string{
		"app":                   "hopper-vm",
		"role":                  "user-vm",
		"hopper.dev/pod-id":     opts.PodID,
		"hopper.dev/user-id":    opts.UserID,
		"hopper.dev/plan":       opts.Plan,
	}

	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      opts.PodName,
			Namespace: pm.namespace,
			Labels:    labels,
		},
		Spec: corev1.PodSpec{
			Containers: []corev1.Container{
				{
					Name:  "vm",
					Image: opts.Image,
					// The hopper/vm-ubuntu image has sshd built in.
					// For other images, fall back to sleep infinity.
					Ports: []corev1.ContainerPort{
						{Name: "ssh", ContainerPort: 22, Protocol: corev1.ProtocolTCP},
						{Name: "vscode", ContainerPort: 8080, Protocol: corev1.ProtocolTCP},
					},
					Env: []corev1.EnvVar{
						// code-server picks this up so asset URLs are relative to the proxy path
						{Name: "CS_BASE_PATH", Value: fmt.Sprintf("/api/pods/%s/vscode", opts.PodID)},
					},
					Resources: corev1.ResourceRequirements{
						Requests: corev1.ResourceList{
							corev1.ResourceCPU:    resource.MustParse(opts.CPU),
							corev1.ResourceMemory: resource.MustParse(opts.Memory),
						},
						Limits: corev1.ResourceList{
							corev1.ResourceCPU:    resource.MustParse(opts.CPU),
							corev1.ResourceMemory: resource.MustParse(opts.Memory),
						},
					},
				},
			},
			RestartPolicy: corev1.RestartPolicyAlways,
		},
	}

	_, err := pm.client.CoreV1().Pods(pm.namespace).Create(ctx, pod, metav1.CreateOptions{})
	if err != nil {
		return PodPorts{}, fmt.Errorf("creating pod %s: %w", opts.PodName, err)
	}

	// Create a NodePort Service so the user can SSH into the pod from outside
	svc := &corev1.Service{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("ssh-%s", opts.PodName),
			Namespace: pm.namespace,
			Labels:    labels,
		},
		Spec: corev1.ServiceSpec{
			Type:     corev1.ServiceTypeNodePort,
			Selector: labels,
			Ports: []corev1.ServicePort{
				{
					Name:       "ssh",
					Port:       22,
					TargetPort: intstr.FromInt32(22),
					Protocol:   corev1.ProtocolTCP,
					// NodePort is auto-assigned by K8s (30000-32767 range)
				},
				{
					Name:       "vscode",
					Port:       8080,
					TargetPort: intstr.FromInt32(8080),
					Protocol:   corev1.ProtocolTCP,
				},
			},
		},
	}

	createdSvc, err := pm.client.CoreV1().Services(pm.namespace).Create(ctx, svc, metav1.CreateOptions{})
	if err != nil {
		// Clean up the pod if service creation fails
		_ = pm.client.CoreV1().Pods(pm.namespace).Delete(ctx, opts.PodName, metav1.DeleteOptions{})
		return PodPorts{}, fmt.Errorf("creating service for %s: %w", opts.PodName, err)
	}

	var ports PodPorts
	for _, p := range createdSvc.Spec.Ports{
		switch p.Name{
		case "ssh":
			ports.SSHPort = p.NodePort
		case "vscode":
			ports.VSCodePort = p.NodePort
		}
	}
	// Return the auto-assigned NodePort
	// sshPort := createdSvc.Spec.Ports[0].NodePort
	return ports, nil
}

// DeletePod removes the K8s Pod and its SSH Service.
func (pm *PodManager) DeletePod(ctx context.Context, podName string) error {
	// Delete the service first
	svcName := fmt.Sprintf("ssh-%s", podName)
	_ = pm.client.CoreV1().Services(pm.namespace).Delete(ctx, svcName, metav1.DeleteOptions{})

	// Delete the pod
	err := pm.client.CoreV1().Pods(pm.namespace).Delete(ctx, podName, metav1.DeleteOptions{})
	if err != nil {
		return fmt.Errorf("deleting pod %s: %w", podName, err)
	}
	return nil
}

// ListNodes returns info about all cluster nodes.
func (pm *PodManager) ListNodes(ctx context.Context) ([]NodeInfo, error) {
	nodes, err := pm.client.CoreV1().Nodes().List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, fmt.Errorf("listing nodes: %w", err)
	}

	// Count pods per node
	pods, err := pm.client.CoreV1().Pods(pm.namespace).List(ctx, metav1.ListOptions{
		LabelSelector: "app=hopper-vm",
	})
	podCountByNode := make(map[string]int)
	if err == nil {
		for _, p := range pods.Items {
			podCountByNode[p.Spec.NodeName]++
		}
	}

	var result []NodeInfo
	for _, n := range nodes.Items {
		ready := false
		for _, c := range n.Status.Conditions {
			if c.Type == corev1.NodeReady && c.Status == corev1.ConditionTrue {
				ready = true
			}
		}

		result = append(result, NodeInfo{
			Name:              n.Name,
			CPUCapacity:       n.Status.Capacity.Cpu().String(),
			MemoryCapacity:    n.Status.Capacity.Memory().String(),
			CPUAllocatable:    n.Status.Allocatable.Cpu().String(),
			MemoryAllocatable: n.Status.Allocatable.Memory().String(),
			PodCount:          podCountByNode[n.Name],
			Ready:             ready,
		})
	}
	return result, nil
}

type NodeInfo struct {
	Name              string
	CPUCapacity       string
	MemoryCapacity    string
	CPUAllocatable    string
	MemoryAllocatable string
	PodCount          int
	Ready             bool
}

// GetPodMetrics fetches resource usage for a specific pod.
// If metrics-server is unavailable, returns limits from the pod spec.
func (pm *PodManager) GetPodMetrics(ctx context.Context, podName string) (*PodMetrics, error) {
	pod, err := pm.client.CoreV1().Pods(pm.namespace).Get(ctx, podName, metav1.GetOptions{})
	if err != nil {
		return nil, fmt.Errorf("getting pod %s: %w", podName, err)
	}

	var memLimit int64
	if len(pod.Spec.Containers) > 0 {
		if ml := pod.Spec.Containers[0].Resources.Limits.Memory(); ml != nil {
			memLimit = ml.Value()
		}
	}

	return &PodMetrics{
		PodName:          podName,
		CPUNanoCores:     0, // Requires metrics-server for live data
		MemoryBytes:      0,
		MemoryLimitBytes: memLimit,
	}, nil
}

type PodMetrics struct {
	PodName          string
	CPUNanoCores     int64
	MemoryBytes      int64
	MemoryLimitBytes int64
}
