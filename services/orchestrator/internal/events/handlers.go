package events

import (
	"context"
	"encoding/json"
	"time"

	"github.com/nats-io/nats.go"
	"go.uber.org/zap"
	apierrors "k8s.io/apimachinery/pkg/api/errors"

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
	js, err := nc.JetStream()
	if err != nil {
		return err
	}

	// When billing is exhausted, auto-terminate the pod. This is a durable
	// JetStream consumer so an orchestrator restart does not drop termination.
	_, err = js.QueueSubscribe(SubjectBillExhaust, "orchestrator-billing-workers", func(msg *nats.Msg) {
		var data struct {
			PodID  string `json:"pod_id"`
			UserID string `json:"user_id"`
		}
		if err := json.Unmarshal(msg.Data, &data); err != nil {
			logger.Error("bad billing.exhausted payload", zap.Error(err))
			_ = msg.Ack()
			return
		}

		logger.Info("credits exhausted — terminating pod",
			zap.String("pod_id", data.PodID),
			zap.String("user_id", data.UserID),
		)

		// Transition state
		_ = podMgr.Transition(data.PodID, pod.StateStopping)

		// Delete K8s resources
		p, ok := podMgr.Get(data.PodID)
		if ev, didStop := ticker.StopAndProrate(data.PodID, time.Now()); didStop && ev.Amount > 0 {
			if err := Publish(nc, SubjectBillDeduct, map[string]interface{}{
				"pod_id":  ev.PodID,
				"amount":  ev.Amount,
				"user_id": data.UserID,
				"tx_id":   ev.TxID,
				"seq":     ev.Seq,
				"final":   true,
			}); err != nil {
				logger.Error("failed to publish final prorated billing event", zap.Error(err))
				_ = msg.Nak()
				return
			}
		}
		if ok {
			if err := k8sMgr.DeletePod(context.Background(), p.PodName); err != nil {
				if apierrors.IsNotFound(err) {
					logger.Info("exhausted pod already deleted", zap.String("pod_id", data.PodID))
				} else {
					logger.Error("failed to delete exhausted pod", zap.Error(err))
					_ = msg.Nak()
					return
				}
			}
		}

		_ = podMgr.Transition(data.PodID, pod.StateTerminated)

		if err := Publish(nc, SubjectPodStopped, map[string]string{
			"pod_id": data.PodID,
			"reason": "credits_exhausted",
		}); err != nil {
			logger.Error("failed to publish exhausted pod stopped event", zap.Error(err))
			_ = msg.Nak()
			return
		}

		_ = msg.Ack()
	},
		nats.BindStream("BILLING"),
		nats.Durable("orchestrator-billing-exhausted"),
		nats.ManualAck(),
	)
	if err != nil {
		return err
	}

	logger.Info("NATS subscriptions registered",
		zap.Strings("subjects", []string{SubjectBillExhaust}),
	)
	return nil
}
