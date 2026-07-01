package events

import (
	"encoding/json"
	"fmt"
	"strings"

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
	if err := ensureStreams(nc); err != nil {
		nc.Close()
		return nil, err
	}
	return nc, nil
}

func ensureStreams(nc *nats.Conn) error {
	js, err := nc.JetStream()
	if err != nil {
		return fmt.Errorf("creating JetStream context: %w", err)
	}
	if _, err := js.StreamInfo("BILLING"); err == nil {
		return nil
	}
	if _, err := js.AddStream(&nats.StreamConfig{
		Name:     "BILLING",
		Subjects: []string{"billing.*"},
		Storage:  nats.FileStorage,
	}); err != nil {
		msg := strings.ToLower(err.Error())
		if !strings.Contains(msg, "already") && !strings.Contains(msg, "in use") {
			return fmt.Errorf("creating BILLING JetStream stream: %w", err)
		}
	}
	return nil
}

func Publish(nc *nats.Conn, subject string, data any) error {
	payload, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("marshaling event: %w", err)
	}
	if strings.HasPrefix(subject, "billing.") {
		js, err := nc.JetStream()
		if err != nil {
			return fmt.Errorf("creating JetStream context: %w", err)
		}
		if _, err := js.Publish(subject, payload); err != nil {
			return fmt.Errorf("publishing JetStream event %s: %w", subject, err)
		}
		return nil
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
