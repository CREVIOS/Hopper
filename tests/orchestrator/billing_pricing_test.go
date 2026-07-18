package orchestrator_test

import (
	"math"
	"testing"
	"time"

	"github.com/hopper/orchestrator/internal/billing"
	"go.uber.org/zap"
)

func TestVMPlanHourlyRates(t *testing.T) {
	tests := []struct {
		name string
		rate float64
	}{
		{name: "small", rate: 1},
		{name: "medium", rate: 2},
		{name: "large", rate: 4},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			plan, ok := billing.Plans[test.name]
			if !ok {
				t.Fatalf("plan %q is missing", test.name)
			}
			if plan.CreditsPerHr != test.rate {
				t.Fatalf("rate = %v, want %v", plan.CreditsPerHr, test.rate)
			}
		})
	}
}

func TestPartialHourBillingUsesPerMinuteRate(t *testing.T) {
	plan := billing.Plans["medium"]
	minutes := 45.0

	charge := minutes * (plan.CreditsPerHr / 60)
	want := 1.5
	if math.Abs(charge-want) > 1e-12 {
		t.Fatalf("45-minute charge = %v, want %v", charge, want)
	}
}

func TestStopAndProrateProducesFinalIdempotencyKey(t *testing.T) {
	ticker := billing.NewTicker(zap.NewNop())
	ticker.Start("pod-1", billing.Plans["large"], func(billing.TickEvent) {})

	event, ok := ticker.StopAndProrate("pod-1", time.Now())
	if !ok {
		t.Fatal("active billing ticker was not stopped")
	}
	if event.PodID != "pod-1" {
		t.Fatalf("pod id = %q, want pod-1", event.PodID)
	}
	if event.Seq != 1 {
		t.Fatalf("final sequence = %d, want 1", event.Seq)
	}
	if event.TxID != "pod-1:final:1" {
		t.Fatalf("final transaction id = %q", event.TxID)
	}
	if event.Amount < 0 {
		t.Fatalf("prorated amount is negative: %v", event.Amount)
	}
}

func TestBillingStopsIdempotently(t *testing.T) {
	ticker := billing.NewTicker(zap.NewNop())
	ticker.Start("pod-1", billing.Plans["small"], func(billing.TickEvent) {})
	ticker.Stop("pod-1")

	if _, ok := ticker.StopAndProrate("pod-1", time.Now()); ok {
		t.Fatal("stopped pod remained billable")
	}
	// Repeated stops must remain safe.
	ticker.Stop("pod-1")
}

func TestZeroRatePlanDoesNotStartBilling(t *testing.T) {
	ticker := billing.NewTicker(zap.NewNop())
	free := billing.VmPlan{Name: "Scavenger", CreditsPerHr: 0}
	ticker.Start("free-pod", free, func(billing.TickEvent) {
		t.Error("zero-rate plan emitted a billing event")
	})

	if _, ok := ticker.StopAndProrate("free-pod", time.Now()); ok {
		t.Fatal("zero-rate plan created a billing timer")
	}
}

func TestUnknownPlanIsNotSilentlyPriced(t *testing.T) {
	if _, ok := billing.Plans["unknown"]; ok {
		t.Fatal("unknown plan unexpectedly has a configured price")
	}
}

func TestTickTxIDIsKeyedToWallClockMinute(t *testing.T) {
	base := time.Date(2026, 7, 17, 10, 5, 30, 0, time.UTC)

	// Same minute → same key: a restarted orchestrator (or a duplicate
	// ticker during a rollout overlap) re-charging the same minute dedupes
	// against the consumer's UNIQUE constraint instead of double-billing.
	sameMinute := billing.TickTxID("pod-1", base.Add(20*time.Second))
	if got := billing.TickTxID("pod-1", base); got != sameMinute {
		t.Fatalf("same-minute ticks produced different tx ids: %q vs %q", got, sameMinute)
	}

	// Next minute → new key: normal consecutive ticks each land a charge.
	if billing.TickTxID("pod-1", base.Add(time.Minute)) == sameMinute {
		t.Fatal("consecutive minutes reused the same tx id")
	}

	// Distinct pods never share keys.
	if billing.TickTxID("pod-2", base) == billing.TickTxID("pod-1", base) {
		t.Fatal("different pods share a tx id")
	}

	// Regression guard for the restart under-billing bug: the key must not
	// look like the old in-memory sequence form (pod-1:1, pod-1:2, ...),
	// which collided with historical rows after a restart.
	if billing.TickTxID("pod-1", base) == "pod-1:1" {
		t.Fatal("tx id fell back to sequence-number form")
	}
}

func TestStartTwiceReplacesTickerWithoutLeaking(t *testing.T) {
	ticker := billing.NewTicker(zap.NewNop())
	ticker.Start("pod-1", billing.Plans["small"], func(billing.TickEvent) {})
	// Second Start (CreatePod racing Reconcile) must supersede the first.
	ticker.Start("pod-1", billing.Plans["large"], func(billing.TickEvent) {})

	event, ok := ticker.StopAndProrate("pod-1", time.Now())
	if !ok {
		t.Fatal("pod was not billable after double Start")
	}
	if event.PodID != "pod-1" {
		t.Fatalf("pod id = %q, want pod-1", event.PodID)
	}
	// And it stopped cleanly — nothing left billable.
	if _, ok := ticker.StopAndProrate("pod-1", time.Now()); ok {
		t.Fatal("double Start leaked a second billing timer")
	}
}
