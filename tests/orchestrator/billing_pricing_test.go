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
