package events

import (
	"encoding/json"
	"fmt"

	"github.com/nats-io/nats.go"
)

func Connect(url string) (*nats.Conn, error) {
	nc, err := nats.Connect(url,
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(-1),
	)
	if err != nil {
		return nil, fmt.Errorf("connecting to NATS: %w", err)
	}
	return nc, nil
}

func Publish(nc *nats.Conn, subject string, data any) error {
	payload, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("marshaling event: %w", err)
	}
	return nc.Publish(subject, payload)
}

func Subscribe(nc *nats.Conn, subject string, handler func(msg *nats.Msg)) (*nats.Subscription, error) {
	return nc.Subscribe(subject, handler)
}

// NATS subject constants
const (
	SubjectPodCreated  = "pod.created"
	SubjectPodStarted  = "pod.started"
	SubjectPodStopped  = "pod.stopped"
	SubjectPodFailed   = "pod.failed"
	SubjectBillDeduct  = "billing.deducted"
	SubjectBillExhaust = "billing.exhausted"
	SubjectBillAlloc   = "billing.allocated"
)
