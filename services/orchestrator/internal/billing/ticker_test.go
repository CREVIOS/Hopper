package billing

import (
	"testing"
	"time"

	"go.uber.org/zap"
)

func TestStopAndProrateReturnsFinalCharge(t *testing.T) {
	ticker := NewTicker(zap.NewNop())
	ticker.Start("pod-1", VmPlan{Name: "Test", CreditsPerHr: 60}, func(TickEvent) {})

	ev, ok := ticker.StopAndProrate("pod-1", time.Now().Add(30*time.Second))
	if !ok {
		t.Fatal("expected active billing timer")
	}
	if ev.TxID != "pod-1:final:1" {
		t.Fatalf("unexpected final tx id: %s", ev.TxID)
	}
	if ev.Amount < 0.49 || ev.Amount > 0.51 {
		t.Fatalf("expected about 0.5 credits, got %f", ev.Amount)
	}

	if _, ok := ticker.StopAndProrate("pod-1", time.Now()); ok {
		t.Fatal("timer should be removed after final proration")
	}
}
