package events

import (
	"context"
	"fmt"
	"time"

	"github.com/nats-io/nats.go"
	"go.uber.org/zap"

	"github.com/hopper/orchestrator/internal/k8s"
	"github.com/hopper/orchestrator/internal/pod"
)

// StartMetricsPublisher runs a background loop that publishes CPU/memory
// metrics for all running pods to NATS every 5 seconds.
func StartMetricsPublisher(
	ctx context.Context,
	nc *nats.Conn,
	logger *zap.Logger,
	podMgr *pod.Manager,
	k8sMgr *k8s.PodManager,
) {
	ticker := time.NewTicker(5 * time.Second)
	go func() {
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				pods := podMgr.ListRunning()
				for _, p := range pods {
					metrics, err := k8sMgr.GetPodMetrics(ctx, p.PodName)
					if err != nil {
						logger.Debug("metrics fetch failed",
							zap.String("pod", p.PodName),
							zap.Error(err),
						)
						continue
					}

					_ = Publish(nc, fmt.Sprintf("metrics.%s", p.ID), map[string]interface{}{
						"pod_id":             p.ID,
						"cpu_percent":        float64(metrics.CPUNanoCores) / 1e9 * 100,
						"memory_used_bytes":  metrics.MemoryBytes,
						"memory_limit_bytes": metrics.MemoryLimitBytes,
					})
				}
			}
		}
	}()
	logger.Info("metrics publisher started (5s interval)")
}
