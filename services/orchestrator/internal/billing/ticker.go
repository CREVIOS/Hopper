package billing

import (
	"context"
	"sync"
	"time"

	"go.uber.org/zap"
)

type podBilling struct {
	cancel       context.CancelFunc
	startTime    time.Time
	lastTickTime time.Time
	tickSeq      uint64 // monotonic sequence within a pod's lifetime, for tx_id
	plan         VmPlan
}

type Ticker struct {
	mu     sync.Mutex
	timers map[string]*podBilling
	logger *zap.Logger
}

func NewTicker(logger *zap.Logger) *Ticker {
	return &Ticker{
		timers: make(map[string]*podBilling),
		logger: logger,
	}
}

// TickEvent is what the orchestrator publishes per billing tick. The tx_id
// is deterministic: same (pod_id, seq) produces the same tx_id, so a NATS
// JetStream redelivery hits the consumer's UNIQUE constraint and dedupes.
type TickEvent struct {
	PodID  string
	Amount float64
	TxID   string
	Seq    uint64
}

// OnTickFunc is invoked with a fully-formed billing event including a
// deterministic tx_id for idempotency in the consumer.
type OnTickFunc func(ev TickEvent)

func (t *Ticker) Start(podID string, plan VmPlan, onTick OnTickFunc) {
	if plan.CreditsPerHr == 0 {
		return
	}

	ctx, cancel := context.WithCancel(context.Background())
	now := time.Now()

	t.mu.Lock()
	t.timers[podID] = &podBilling{
		cancel:       cancel,
		startTime:    now,
		lastTickTime: now,
		plan:         plan,
	}
	t.mu.Unlock()

	creditsPerMinute := plan.CreditsPerHr / 60.0

	go func() {
		ticker := time.NewTicker(1 * time.Minute)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				var seq uint64
				t.mu.Lock()
				pb, ok := t.timers[podID]
				if ok {
					pb.tickSeq++
					seq = pb.tickSeq
					pb.lastTickTime = time.Now()
				}
				t.mu.Unlock()
				if !ok {
					return
				}
				onTick(TickEvent{
					PodID:  podID,
					Amount: creditsPerMinute,
					Seq:    seq,
					TxID:   podID + ":" + formatUint(seq),
				})
			}
		}
	}()

	t.logger.Info("billing started", zap.String("pod_id", podID), zap.Float64("rate_per_hr", plan.CreditsPerHr))
}

func formatUint(n uint64) string {
	// avoid pulling in strconv just for one fmt
	if n == 0 {
		return "0"
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	return string(buf[i:])
}

// StopAndProrate stops billing and returns the prorated charge plus the
// final tick metadata. The caller publishes the final billing event using
// the returned tx_id so the consumer dedupes against any in-flight tick.
func (t *Ticker) StopAndProrate(podID string, stopTime time.Time) (TickEvent, bool) {
	t.mu.Lock()
	defer t.mu.Unlock()

	pb, ok := t.timers[podID]
	if !ok {
		return TickEvent{}, false
	}

	pb.cancel()

	// Anchor the stop time to a caller-supplied timestamp (typically the
	// K8s DeletionTimestamp set atomically when the user clicks Terminate),
	// not time.Now() inside the goroutine — otherwise a delayed scheduler
	// can charge an extra few seconds after the pod is already gone.
	if stopTime.IsZero() || stopTime.Before(pb.lastTickTime) {
		stopTime = time.Now()
	}
	elapsed := stopTime.Sub(pb.lastTickTime)
	if elapsed < 0 {
		elapsed = 0
	}
	creditsPerMinute := pb.plan.CreditsPerHr / 60.0
	prorated := elapsed.Minutes() * creditsPerMinute

	pb.tickSeq++
	ev := TickEvent{
		PodID:  podID,
		Amount: prorated,
		Seq:    pb.tickSeq,
		TxID:   podID + ":final:" + formatUint(pb.tickSeq),
	}

	delete(t.timers, podID)
	t.logger.Info("billing stopped with prorate",
		zap.String("pod_id", podID),
		zap.Float64("prorated_charge", prorated),
		zap.Duration("elapsed_since_tick", elapsed),
	)
	return ev, true
}

func (t *Ticker) Stop(podID string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	if pb, ok := t.timers[podID]; ok {
		pb.cancel()
		delete(t.timers, podID)
		t.logger.Info("billing stopped", zap.String("pod_id", podID))
	}
}
