package events

import (
	"context"
	"encoding/json"

	"github.com/nats-io/nats.go"
	"go.uber.org/zap"

	"github.com/hopper/orchestrator/internal/billing"
	"github.com/hopper/orchestrator/internal/k8s"
	"github.com/hopper/orchestrator/internal/pod"
)

// SubscribeAll sets up NATS subscriptions for reconciliation and billing exhaustion.
func SubscribeAll(
	nc *nats.Conn,
	logger *zap.Logger,
	podMgr *pod.Manager,
	k8sMgr *k8s.PodManager,
	ticker *billing.Ticker,
) error {
	// When billing is exhausted, auto-terminate the pod
	_, err := nc.Subscribe(SubjectBillExhaust, func(msg *nats.Msg) {
		var data struct {
			PodID  string `json:"pod_id"`
			UserID string `json:"user_id"`
		}
		if err := json.Unmarshal(msg.Data, &data); err != nil {
			logger.Error("bad billing.exhausted payload", zap.Error(err))
			return
		}

		logger.Info("credits exhausted — terminating pod",
			zap.String("pod_id", data.PodID),
			zap.String("user_id", data.UserID),
		)

		// Stop billing
		ticker.Stop(data.PodID)

		// Transition state
		_ = podMgr.Transition(data.PodID, pod.StateStopping)

		// Delete K8s resources
		p, ok := podMgr.Get(data.PodID)
		if ok {
			_ = k8sMgr.DeletePod(context.Background(), p.PodName)
		}

		_ = podMgr.Transition(data.PodID, pod.StateTerminated)

		_ = Publish(nc, SubjectPodStopped, map[string]string{
			"pod_id": data.PodID,
			"reason": "credits_exhausted",
		})
	})
	if err != nil {
		return err
	}

	logger.Info("NATS subscriptions registered",
		zap.Strings("subjects", []string{SubjectBillExhaust}),
	)
	return nil
}
