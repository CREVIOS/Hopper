package k8s

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"strings"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"
	"k8s.io/client-go/kubernetes"
	metricsv "k8s.io/metrics/pkg/client/clientset/versioned"
)

// SshPasswordAnnotation stores the per-pod root SSH password on the K8s Pod
// object so it can be recovered on orchestrator restart (reconciliation) without
// a separate secret store.
const SshPasswordAnnotation = "hopper.dev/ssh-password"

// generateRandomPassword returns a 24-char URL-safe random string (192 bits
// of entropy). Used for the per-pod SSH root password. (code-server runs with
// auth disabled — the platform gates VS Code access, so no code-server
// password is generated; see images/hopper-vm/config/code-server-config.yaml.)
func generateRandomPassword() (string, error) {
	buf := make([]byte, 18)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}

// containerStartupArgs is the `/bin/sh -c` script the VM container runs on
// boot: set the per-pod root password, then — only if the launching user
// registered SSH keys — materialise them into /root/.ssh/authorized_keys
// before sshd starts, and finally exec supervisord (sshd + code-server).
//
// $AUTHORIZED_KEYS (newline-joined public keys) is quoted everywhere so its
// contents are never interpreted by the shell. The `[ -z ] ||` guard makes the
// key step a no-op for password-only VMs, preserving prior behaviour. `exec`
// replaces the shell so SIGTERM reaches supervisord for graceful shutdown.
func containerStartupArgs() string {
	return `echo "root:$ROOT_PASSWORD" | chpasswd && ` +
		`{ [ -z "$AUTHORIZED_KEYS" ] || { mkdir -p /root/.ssh && ` +
		`printf '%s\n' "$AUTHORIZED_KEYS" > /root/.ssh/authorized_keys && ` +
		`chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys; }; } && ` +
		`exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf`
}

type PodManager struct {
	client    *kubernetes.Clientset
	metrics   *metricsv.Clientset
	namespace string
}

func NewPodManager(client *kubernetes.Clientset, namespace string) *PodManager {
	return &PodManager{client: client, namespace: namespace}
}

// SetMetricsClient wires in the metrics-server client used by GetPodMetrics.
// Optional — without it, GetPodMetrics still returns the configured limit
// (so memory_limit_bytes is correct) but used CPU/memory stay at zero.
func (pm *PodManager) SetMetricsClient(m *metricsv.Clientset) {
	pm.metrics = m
}

type CreatePodOpts struct {
	PodName string
	PodID   string
	UserID  string
	Plan    string
	Image   string
	CPU     string
	Memory  string
	// DiskGiB is the requested workspace size. When >0 a PVC is created and
	// mounted at /workspace so the user's files survive pod restarts.
	DiskGiB int
	// StorageClass is the K8s StorageClassName for the workspace PVC. Empty
	// uses the cluster default.
	StorageClass string
	// AuthorizedKeys are the launching user's OpenSSH public keys. When
	// non-empty they are written to /root/.ssh/authorized_keys in the VM so
	// key-based SSH works. Public keys are not secret; they are passed as a
	// pod env var and materialised by the container's startup command.
	AuthorizedKeys []string
	// WorkspacePVCName, when set, is the user's persistent ReadWriteOnce PVC
	// (ws-user-<id>, FR-HC-28). It is ensured lazily (created if absent, reused
	// otherwise), mounted read-write at /workspace, and — because its name is
	// outside DeletePod's ws-<pod> scope — never deleted by the session
	// lifecycle. Takes precedence over the legacy per-pod DiskGiB path.
	WorkspacePVCName    string
	WorkspaceCapacityGB int
}

type PodPorts struct {
	SSHPort     int32
	VSCodePort  int32
	SSHPassword string
}

// cpuRequestFor returns the scheduling CPU request for a VM: a quarter of the
// plan's CPU limit, floored at 100m. VMs spend almost all their time idle, so
// reserving the full limit wastes node capacity and blocks new VMs from
// scheduling; a fractional request lets them bin-pack while CPU limits still
// cap bursts.
func cpuRequestFor(cpuLimit string) resource.Quantity {
	q := resource.MustParse(cpuLimit)
	m := q.MilliValue() / 4
	if m < 100 {
		m = 100
	}
	return *resource.NewMilliQuantity(m, resource.DecimalSI)
}

// CreatePod creates a K8s Pod with resource limits and a NodePort Service for SSH.
// Returns the assigned SSH NodePort and the per-pod root password.
func (pm *PodManager) CreatePod(ctx context.Context, opts CreatePodOpts) (PodPorts, error) {
	labels := map[string]string{
		"app":                "hopper-vm",
		"role":               "user-vm",
		"hopper.dev/pod-id":  opts.PodID,
		"hopper.dev/user-id": opts.UserID,
		"hopper.dev/plan":    opts.Plan,
	}

	sshPassword, err := generateRandomPassword()
	if err != nil {
		return PodPorts{}, fmt.Errorf("generating ssh password: %w", err)
	}

	// LXCFS bind-mounts: make /proc/{meminfo,cpuinfo,...} reflect the pod's
	// cgroup limits instead of the host's totals. Without this, `free -h`
	// inside the VM shows the node's RAM and `nproc` shows all host cores —
	// a tenant-isolation leak. The lxcfs daemon must be running on every node
	// (systemd unit `lxcfs.service`).
	// Resolve the /workspace-backing PVC (created BEFORE the Pod so the kubelet
	// doesn't loop on a missing claim):
	//   - Persistent per-user workspace (FR-HC-28): opts.WorkspacePVCName set →
	//     ensure a RWO PVC exists (create-if-absent, reuse otherwise). It has no
	//     pod owner-reference and its ws-user-<id> name is outside DeletePod's
	//     ws-<pod> scope, so it survives the pod and is reused across sessions.
	//   - Legacy per-pod disk: opts.DiskGiB>0 → a pod-scoped ws-<pod> PVC that
	//     DeletePod removes with the pod (unused today; kept for compatibility).
	workspacePVC := ""
	workspaceSizeGi := 0
	switch {
	case opts.WorkspacePVCName != "":
		workspacePVC, workspaceSizeGi = opts.WorkspacePVCName, opts.WorkspaceCapacityGB
	case opts.DiskGiB > 0:
		workspacePVC, workspaceSizeGi = fmt.Sprintf("ws-%s", opts.PodName), opts.DiskGiB
	}
	if workspacePVC != "" {
		pvc := &corev1.PersistentVolumeClaim{
			ObjectMeta: metav1.ObjectMeta{
				Name:      workspacePVC,
				Namespace: pm.namespace,
				Labels:    labels,
			},
			Spec: corev1.PersistentVolumeClaimSpec{
				AccessModes: []corev1.PersistentVolumeAccessMode{corev1.ReadWriteOnce},
				Resources: corev1.VolumeResourceRequirements{
					Requests: corev1.ResourceList{
						corev1.ResourceStorage: resource.MustParse(fmt.Sprintf("%dGi", workspaceSizeGi)),
					},
				},
			},
		}
		if opts.StorageClass != "" {
			pvc.Spec.StorageClassName = &opts.StorageClass
		}
		// Idempotent: a returning user already has their workspace PVC, so
		// AlreadyExists means "reuse it" (keep the data), not an error.
		if _, err := pm.client.CoreV1().PersistentVolumeClaims(pm.namespace).Create(ctx, pvc, metav1.CreateOptions{}); err != nil && !apierrors.IsAlreadyExists(err) {
			return PodPorts{}, fmt.Errorf("ensuring workspace pvc: %w", err)
		}
	}

	lxcfsFiles := []string{"meminfo", "cpuinfo", "stat", "uptime", "diskstats", "swaps", "loadavg"}
	hostPathFile := corev1.HostPathFile
	var lxcfsVolumes []corev1.Volume
	var lxcfsMounts []corev1.VolumeMount
	for _, f := range lxcfsFiles {
		volName := "lxcfs-" + f
		lxcfsVolumes = append(lxcfsVolumes, corev1.Volume{
			Name: volName,
			VolumeSource: corev1.VolumeSource{
				HostPath: &corev1.HostPathVolumeSource{
					Path: "/var/lib/lxcfs/proc/" + f,
					Type: &hostPathFile,
				},
			},
		})
		lxcfsMounts = append(lxcfsMounts, corev1.VolumeMount{
			Name:      volName,
			MountPath: "/proc/" + f,
			ReadOnly:  true,
		})
	}

	automount := false
	dropAll := corev1.Capability("ALL")
	allowedCaps := []corev1.Capability{
		// Minimum set needed for sshd + PAM login inside the VM.
		// AUDIT_WRITE is required by PAM's pam_loginuid — without it sshd
		// prints "linux_audit_write_entry failed: Operation not permitted"
		// on every connection (login still succeeds, but it's noise).
		// SETGID/SETUID are required by sshd's privilege separation — without
		// them, the privsep child fails setgroups() with EPERM during the
		// pre-auth phase ("setgroups: Operation not permitted [preauth]") and
		// every connection dies as "kex_exchange_identification: Connection
		// closed by remote host". The earlier comment claiming these are
		// optional was wrong: sshd can't accept *any* connection without them.
		// Adding them only allows UID/GID changes *inside* the container,
		// which is bounded by the container's user namespace; it does not
		// weaken the cluster's pod-level isolation.
		"AUDIT_WRITE", "CHOWN", "FOWNER", "FSETID", "KILL",
		"NET_BIND_SERVICE", "SETGID", "SETUID", "SYS_CHROOT",
	}

	// Short grace period: when the user clicks Terminate we want their open
	// ssh sessions to see "Connection closed by remote host" (sshd SIGTERM
	// emits SSH_DISCONNECT) instead of waiting for TCP to time out, so we cap
	// total termination at 5s and run pkill on sshd as a preStop.
	gracePeriod := int64(5)
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      opts.PodName,
			Namespace: pm.namespace,
			Labels:    labels,
			// Stored on the Pod so reconciliation after orchestrator restart can
			// recover the SSH password without an extra Secret.
			Annotations: map[string]string{
				SshPasswordAnnotation: sshPassword,
			},
		},
		Spec: corev1.PodSpec{
			TerminationGracePeriodSeconds: &gracePeriod,
			// Don't expose the orchestrator's K8s API token inside user VMs —
			// otherwise a user with shell access can hit the cluster API.
			AutomountServiceAccountToken: &automount,
			// Use the runtime's default seccomp profile (blocks ~70 syscalls).
			SecurityContext: &corev1.PodSecurityContext{
				SeccompProfile: &corev1.SeccompProfile{Type: corev1.SeccompProfileTypeRuntimeDefault},
			},
			Volumes: append(lxcfsVolumes, func() []corev1.Volume {
				if workspacePVC == "" {
					return nil
				}
				return []corev1.Volume{{
					Name: "workspace",
					VolumeSource: corev1.VolumeSource{
						PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
							ClaimName: workspacePVC,
						},
					},
				}}
			}()...),
			Containers: []corev1.Container{
				{
					Name:  "vm",
					Image: opts.Image,
					// VM images (hopper/vm-*:22.04) are built locally and imported
					// into the node's containerd (`make vm-images-load`); they are
					// NOT in a pullable registry. IfNotPresent uses the local copy
					// and never reaches out to Docker Hub (which would fail with
					// ErrImagePull). If the image is ever evicted from the node,
					// rebuild+reimport it — a missing image is the one thing that
					// makes a "created" VM never actually run.
					ImagePullPolicy: corev1.PullIfNotPresent,
					// Override the image CMD so we can set a unique root password
					// from $ROOT_PASSWORD before sshd comes up. exec replaces the
					// shell so signals reach supervisord normally.
					Command: []string{"/bin/sh", "-c"},
					Args:    []string{containerStartupArgs()},
					Ports: []corev1.ContainerPort{
						{Name: "ssh", ContainerPort: 22, Protocol: corev1.ProtocolTCP},
						{Name: "vscode", ContainerPort: 8080, Protocol: corev1.ProtocolTCP},
					},
					Env: []corev1.EnvVar{
						// code-server picks this up so asset URLs are relative to the proxy path.
						// Path-based routing: /{userId}/code/{podId} (see ingress + frontend iframe).
						{Name: "CS_BASE_PATH", Value: fmt.Sprintf("/%s/code/%s", opts.UserID, opts.PodID)},
						{Name: "ROOT_PASSWORD", Value: sshPassword},
						// Newline-joined OpenSSH public keys (empty ⇒ no key injection).
						{Name: "AUTHORIZED_KEYS", Value: strings.Join(opts.AuthorizedKeys, "\n")},
					},
					Resources: corev1.ResourceRequirements{
						// CPU request is a fraction of the limit so near-idle VMs
						// bin-pack onto the node while still bursting to the full
						// plan CPU. Memory is far less elastic (OOM-kills, no
						// reclaim), so its request stays pinned to the limit.
						Requests: corev1.ResourceList{
							corev1.ResourceCPU:    cpuRequestFor(opts.CPU),
							corev1.ResourceMemory: resource.MustParse(opts.Memory),
						},
						Limits: corev1.ResourceList{
							corev1.ResourceCPU:    resource.MustParse(opts.CPU),
							corev1.ResourceMemory: resource.MustParse(opts.Memory),
						},
					},
					// Drop all caps then re-add only what sshd / apt need.
					// NET_RAW is dropped — blocks raw-socket abuse (nmap -sS,
					// scapy etc.) without breaking normal TCP/UDP usage.
					SecurityContext: &corev1.SecurityContext{
						AllowPrivilegeEscalation: &automount, // false
						Capabilities: &corev1.Capabilities{
							Drop: []corev1.Capability{dropAll},
							Add:  allowedCaps,
						},
					},
					// preStop runs before kubelet sends SIGTERM. SIGHUPing sshd
					// makes it disconnect every open client cleanly so users
					// see "Connection closed by remote host." rather than the
					// 30-90s "Read from remote host … Operation timed out" the
					// kernel produces when the network namespace is torn down
					// from underneath an established TCP session.
					Lifecycle: &corev1.Lifecycle{
						PreStop: &corev1.LifecycleHandler{
							Exec: &corev1.ExecAction{
								Command: []string{"/bin/sh", "-c", "pkill -HUP sshd 2>/dev/null || true; sleep 1"},
							},
						},
					},
					VolumeMounts: append(lxcfsMounts, func() []corev1.VolumeMount {
						if workspacePVC == "" {
							return nil
						}
						return []corev1.VolumeMount{{
							Name:      "workspace",
							MountPath: "/workspace",
						}}
					}()...),
				},
			},
			RestartPolicy: corev1.RestartPolicyAlways,
		},
	}

	_, err = pm.client.CoreV1().Pods(pm.namespace).Create(ctx, pod, metav1.CreateOptions{})
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

	ports := PodPorts{SSHPassword: sshPassword}
	for _, p := range createdSvc.Spec.Ports {
		switch p.Name {
		case "ssh":
			ports.SSHPort = p.NodePort
		case "vscode":
			ports.VSCodePort = p.NodePort
		}
	}
	return ports, nil
}

// DeletePod removes the K8s Pod, its SSH Service, and its workspace PVC.
//
// Order matters:
//  1. Delete the Service so new SSH connections fail fast with "Connection
//     refused" rather than landing on a sshd about to be SIGTERMed.
//  2. Delete the Pod (preStop SIGHUPs sshd so existing sessions see a clean
//     "Connection closed by remote host." instead of a TCP timeout).
//  3. Delete the PVC. The user explicitly terminated the VM — keeping the
//     disk around would silently rack up storage charges. (If we ever offer
//     "stop without delete", split this into Delete vs StopOnly.)
func (pm *PodManager) DeletePod(ctx context.Context, podName string) error {
	svcName := fmt.Sprintf("ssh-%s", podName)
	_ = pm.client.CoreV1().Services(pm.namespace).Delete(ctx, svcName, metav1.DeleteOptions{})

	grace := int64(5)
	err := pm.client.CoreV1().Pods(pm.namespace).Delete(
		ctx, podName,
		metav1.DeleteOptions{GracePeriodSeconds: &grace},
	)
	if err != nil {
		return fmt.Errorf("deleting pod %s: %w", podName, err)
	}

	pvcName := fmt.Sprintf("ws-%s", podName)
	_ = pm.client.CoreV1().PersistentVolumeClaims(pm.namespace).Delete(ctx, pvcName, metav1.DeleteOptions{})
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

// GetPodMetrics fetches resource usage for a specific pod from
// metrics-server (live CPU/RAM) and the spec (limits). When the metrics
// client isn't wired up or metrics-server hasn't sampled the pod yet,
// usage falls back to zero so the gateway still sees a publishable event.
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

	out := &PodMetrics{PodName: podName, MemoryLimitBytes: memLimit}

	if pm.metrics == nil {
		return out, nil
	}
	pm_, err := pm.metrics.MetricsV1beta1().PodMetricses(pm.namespace).Get(ctx, podName, metav1.GetOptions{})
	if err != nil {
		// metrics-server may be missing or hasn't sampled the pod yet — return
		// limits-only metrics rather than failing the whole stream.
		return out, nil
	}
	for _, c := range pm_.Containers {
		out.CPUNanoCores += c.Usage.Cpu().ScaledValue(resource.Nano)
		out.MemoryBytes += c.Usage.Memory().Value()
	}
	return out, nil
}

type PodMetrics struct {
	PodName          string
	CPUNanoCores     int64
	MemoryBytes      int64
	MemoryLimitBytes int64
}
