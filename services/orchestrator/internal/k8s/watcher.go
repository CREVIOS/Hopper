package k8s

import (
	"context"
	"fmt"
	"strconv"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/kubernetes"
	"go.uber.org/zap"

	"github.com/hopper/orchestrator/internal/billing"
	"github.com/hopper/orchestrator/internal/pod"
)

// PublishFunc is a callback for publishing NATS events without importing the events package.
type PublishFunc func(subject string, data any) error

type PodWatcher struct {
	client    *kubernetes.Clientset
	namespace string
	logger    *zap.Logger
	publish   PublishFunc
}

func NewPodWatcher(client *kubernetes.Clientset, namespace string, logger *zap.Logger, publish PublishFunc) *PodWatcher {
	return &PodWatcher{client: client, namespace: namespace, logger: logger, publish: publish}
}

// Reconcile rebuilds in-memory state from existing K8s pods on startup.
func (w *PodWatcher) Reconcile(ctx context.Context, podMgr *pod.Manager, ticker *billing.Ticker) {
	pods, err := w.client.CoreV1().Pods(w.namespace).List(ctx, metav1.ListOptions{
		LabelSelector: "app=hopper-vm",
	})
	if err != nil {
		w.logger.Error("reconciliation failed: could not list pods", zap.Error(err))
		return
	}

	for _, p := range pods.Items {
		podID := p.Labels["hopper.dev/pod-id"]
		userID := p.Labels["hopper.dev/user-id"]
		plan := p.Labels["hopper.dev/plan"]
		if podID == "" || userID == "" {
			continue
		}

		// Register in memory
		mgdPod, err := podMgr.Create(pod.CreateOpts{
			ID:        podID,
			UserID:    userID,
			Plan:      plan,
			Image:     p.Spec.Containers[0].Image,
			CPU:       p.Spec.Containers[0].Resources.Limits.Cpu().String(),
			Memory:    p.Spec.Containers[0].Resources.Limits.Memory().String(),
			Namespace: w.namespace,
			PodName:   p.Name,
		})
		if err != nil {
			continue
		}

		// Set state based on K8s phase
		targetState := k8sPhaseToState(p.Status.Phase)
		podMgr.SetState(mgdPod.ID, targetState)

		// Look up SSH port from the service
		svcName := fmt.Sprintf("ssh-%s", p.Name)
		svc, err := w.client.CoreV1().Services(w.namespace).Get(ctx, svcName, metav1.GetOptions{})
		if err == nil {
			var sshPort, vscodePort int32
			for _, sp := range svc.Spec.Ports {
				switch sp.Name {
				case "ssh":
					sshPort = sp.NodePort
				case "vscode":
					vscodePort = sp.NodePort
				}
			}
			podMgr.SetPorts(mgdPod.ID, sshPort, vscodePort)
		}

		// Recover the per-pod root password stashed at create time.
		if pw := p.Annotations[SshPasswordAnnotation]; pw != "" {
			podMgr.SetSshPassword(mgdPod.ID, pw)
		}

		// Restart billing for running pods. Prefer the rate stashed on the pod at
		// create time (the gateway-supplied, possibly admin-edited price); fall
		// back to the built-in Plans map for pods created before the annotation
		// existed.
		if targetState == pod.StateRunning {
			annotatedRate, _ := strconv.ParseFloat(p.Annotations[CreditsPerHrAnnotation], 64)
			rate := billing.ResolveRate(annotatedRate, plan)
			if rate > 0 {
				ticker.Start(mgdPod.ID, billing.VmPlan{Name: plan, CreditsPerHr: rate}, func(ev billing.TickEvent) {
					_ = w.publish("billing.deducted", map[string]interface{}{
						"pod_id":  ev.PodID,
						"amount":  ev.Amount,
						"user_id": userID,
						"tx_id":   ev.TxID,
						"seq":     ev.Seq,
					})
				})
			}
		}

		w.logger.Info("reconciled pod",
			zap.String("pod_id", podID),
			zap.String("state", string(targetState)),
			zap.String("k8s_name", p.Name),
		)
	}

	w.logger.Info("reconciliation complete", zap.Int("pods_recovered", len(pods.Items)))
}

// Watch starts a continuous K8s watch loop that syncs pod state changes.
func (w *PodWatcher) Watch(ctx context.Context, podMgr *pod.Manager, ticker *billing.Ticker) {
	for {
		if ctx.Err() != nil {
			return
		}
		w.watchOnce(ctx, podMgr, ticker)
	}
}

func (w *PodWatcher) watchOnce(ctx context.Context, podMgr *pod.Manager, ticker *billing.Ticker) {
	watcher, err := w.client.CoreV1().Pods(w.namespace).Watch(ctx, metav1.ListOptions{
		LabelSelector: "app=hopper-vm",
	})
	if err != nil {
		w.logger.Error("watch failed", zap.Error(err))
		return
	}
	defer watcher.Stop()

	for event := range watcher.ResultChan() {
		if ctx.Err() != nil {
			return
		}

		p, ok := event.Object.(*corev1.Pod)
		if !ok {
			continue
		}

		podID := p.Labels["hopper.dev/pod-id"]
		if podID == "" {
			continue
		}

		switch event.Type {
		case watch.Modified:
			targetState := k8sPhaseToState(p.Status.Phase)
			mgdPod, exists := podMgr.Get(podID)
			if exists && mgdPod.State != targetState {
				podMgr.SetState(podID, targetState)
				w.logger.Info("pod state synced",
					zap.String("pod_id", podID),
					zap.String("new_state", string(targetState)),
				)

				if targetState == pod.StateFailed || targetState == pod.StateTerminated {
					ticker.Stop(podID)
					_ = w.publish("pod.stopped", map[string]string{
						"pod_id": podID, "reason": "k8s_" + string(p.Status.Phase),
					})
				}
			}

		case watch.Deleted:
			ticker.Stop(podID)
			podMgr.SetState(podID, pod.StateTerminated)
			_ = w.publish("pod.stopped", map[string]string{
				"pod_id": podID, "reason": "deleted",
			})
			w.logger.Info("pod deleted externally", zap.String("pod_id", podID))
		}
	}
}

func k8sPhaseToState(phase corev1.PodPhase) pod.State {
	switch phase {
	case corev1.PodPending:
		return pod.StateCreating
	case corev1.PodRunning:
		return pod.StateRunning
	case corev1.PodSucceeded:
		return pod.StateTerminated
	case corev1.PodFailed:
		return pod.StateFailed
	default:
		return pod.StatePending
	}
}

