package k8s

import (
	"context"
	"time"

	"go.uber.org/zap"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"github.com/hopper/orchestrator/internal/pod"
)

// unschedulableReason returns a short user-facing reason if the pod has been
// stuck Pending for longer than maxPending because the scheduler could not
// place it, or "" if the pod is fine (running, briefly pending, or pending for
// some other reason like image pull that the watchdog should not reap).
//
// Pulled out as a pure function of the pod and a reference time so the decision
// is unit-testable without a live cluster or a real clock.
func unschedulableReason(p *corev1.Pod, now time.Time, maxPending time.Duration) string {
	if p.Status.Phase != corev1.PodPending {
		return ""
	}
	if now.Sub(p.CreationTimestamp.Time) < maxPending {
		return ""
	}
	// Only reap pods the scheduler actively failed to place. A PodScheduled
	// condition with status False and reason Unschedulable is exactly that; a
	// pod pending for other reasons (pulling an image, waiting on a volume) has
	// either no such condition or a different reason, and must be left alone.
	for _, c := range p.Status.Conditions {
		if c.Type == corev1.PodScheduled && c.Status == corev1.ConditionFalse {
			if c.Message != "" {
				return c.Message
			}
			return "no node has room for this VM right now"
		}
	}
	return ""
}

// reapUnschedulableOnce is the single-pass body, kept separate so the loop in
// StartWatchdog stays trivial. It lists VM pods, reaps the ones that are stuck,
// and returns how many it reaped (for logging/tests).
//
// This is the safety net for the fragmentation case on multi-node clusters: the
// admission gate checks aggregate (and per-node) capacity, but placement can
// still fail, and without this the pod would sit Pending forever. Billing never
// started (that waits for Running), so the only harm being undone here is a VM
// stuck "creating".
func (w *PodWatcher) reapUnschedulableOnce(ctx context.Context, podMgr *pod.Manager, pm *PodManager, maxPending time.Duration) int {
	pods, err := w.client.CoreV1().Pods(w.namespace).List(ctx, metav1.ListOptions{
		LabelSelector: "app=hopper-vm",
	})
	if err != nil {
		w.logger.Warn("watchdog: listing pods failed", zap.Error(err))
		return 0
	}

	now := time.Now()
	reaped := 0
	for i := range pods.Items {
		p := &pods.Items[i]
		reason := unschedulableReason(p, now, maxPending)
		if reason == "" {
			continue
		}

		podID := p.Labels["hopper.dev/pod-id"]
		userID := p.Labels["hopper.dev/user-id"]

		// Re-check against a fresh read right before deleting: the decision above
		// used a list snapshot, and a pod can get scheduled (and start running)
		// in the gap. Without this a VM that just became healthy could be reaped.
		// A GET failure (e.g. already gone) falls through to delete, which is
		// idempotent.
		if fresh, err := w.client.CoreV1().Pods(w.namespace).Get(ctx, p.Name, metav1.GetOptions{}); err == nil {
			if unschedulableReason(fresh, time.Now(), maxPending) == "" {
				continue // no longer stuck — leave it alone
			}
		}

		// Mark the managed pod Terminated BEFORE deleting so the watch loop's
		// Deleted handler treats this as an intentional termination and does not
		// also publish pod.stopped (we own the pod.failed below). This goes
		// through the manager's mutex; we deliberately do NOT touch w.lastPhase
		// here — it is owned solely by the watch goroutine, which cleans up its
		// own entry on the Deleted event. Reaching into it from this goroutine
		// would be a data race.
		if mgd, ok := podMgr.GetByPodName(p.Name); ok {
			podMgr.SetState(mgd.ID, pod.StateTerminated)
		}

		if err := pm.DeletePod(ctx, p.Name); err != nil {
			w.logger.Warn("watchdog: deleting unschedulable pod failed",
				zap.String("pod", p.Name), zap.Error(err))
			continue
		}

		// Report the failure so the gateway flips the session to failed, frees
		// the capacity it was holding, and notifies the user. notify=true tells
		// the consumer to send a user-facing message: unlike a synchronous
		// CreatePod failure, nothing else is on the hook to do it here.
		_ = w.publish("pod.failed", map[string]string{
			"pod_id":     podID,
			"api_pod_id": podID,
			"user_id":    userID,
			"reason":     "unschedulable",
			"detail":     reason,
			"notify":     "true",
		})
		w.logger.Info("watchdog: reaped unschedulable VM",
			zap.String("pod_id", podID),
			zap.String("k8s_name", p.Name),
			zap.String("detail", reason),
		)
		reaped++
	}
	return reaped
}

// StartWatchdog runs reapUnschedulableOnce on a ticker until ctx is done. The
// tick is a fraction of maxPending so a stuck pod is caught within roughly one
// extra interval of its deadline. A disabled watchdog (maxPending == 0) is a
// no-op.
func (w *PodWatcher) StartWatchdog(ctx context.Context, podMgr *pod.Manager, pm *PodManager, maxPending time.Duration) {
	if maxPending <= 0 {
		w.logger.Info("scheduling watchdog disabled")
		return
	}
	interval := maxPending / 2
	if interval < 15*time.Second {
		interval = 15 * time.Second
	}
	w.logger.Info("scheduling watchdog started",
		zap.Duration("max_pending", maxPending),
		zap.Duration("interval", interval),
	)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			w.reapUnschedulableOnce(ctx, podMgr, pm, maxPending)
		}
	}
}
