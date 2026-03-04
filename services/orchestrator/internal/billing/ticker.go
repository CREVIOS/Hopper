package billing

import (
	"context"
	"sync"
	"time"

	"go.uber.org/zap"
)

type Ticker struct {
	mu      sync.Mutex
	timers  map[string]context.CancelFunc
	logger  *zap.Logger
}

func NewTicker(logger *zap.Logger) *Ticker {
	return &Ticker{
		timers: make(map[string]context.CancelFunc),
		logger: logger,
	}
}

func (t *Ticker) Start(podID string, tier GpuTier, onTick func(podID string, amount float64)) {
	if tier.CreditsPerHr == 0 {
		return // Scavenger tier: no billing
	}

	ctx, cancel := context.WithCancel(context.Background())

	t.mu.Lock()
	t.timers[podID] = cancel
	t.mu.Unlock()

	creditsPerMinute := tier.CreditsPerHr / 60.0

	go func() {
		ticker := time.NewTicker(1 * time.Minute)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				onTick(podID, creditsPerMinute)
			}
		}
	}()

	t.logger.Info("billing started", zap.String("pod_id", podID), zap.Float64("rate_per_hr", tier.CreditsPerHr))
}

func (t *Ticker) Stop(podID string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	if cancel, ok := t.timers[podID]; ok {
		cancel()
		delete(t.timers, podID)
		t.logger.Info("billing stopped", zap.String("pod_id", podID))
	}
}
