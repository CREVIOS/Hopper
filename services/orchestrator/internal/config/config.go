package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	GRPCPort      int
	NatsURL       string
	KubeConfig    string
	KubeNamespace string
	// LeaderElection gates the singleton work (billing tickers, pod watcher,
	// exhaustion handling, metrics publishing) behind a K8s Lease so two
	// orchestrator instances — e.g. during a rolling update — never bill the
	// same pods twice. Enabled in the K8s deployment; off for local dev,
	// where there is exactly one instance and no Lease API worth requiring.
	LeaderElection bool
	// PendingReapAfter is how long a VM pod may stay unschedulable (Pending
	// with a scheduling failure) before the watchdog deletes it and reports the
	// failure. Its job is fragmentation on multi-node clusters: a VM the
	// admission gate lets through can still find no single node with room and
	// would otherwise sit Pending forever. 0 disables the watchdog.
	PendingReapAfter time.Duration
}

func Load() (*Config, error) {
	cfg := &Config{
		GRPCPort:         50051,
		NatsURL:          getEnv("HOPPER_NATS_URL", "nats://localhost:4222"),
		KubeConfig:       getEnv("KUBECONFIG", ""),
		KubeNamespace:    getEnv("KUBERNETES_NAMESPACE", "hopper"),
		LeaderElection:   getEnv("HOPPER_LEADER_ELECTION", "false") == "true",
		PendingReapAfter: getEnvDuration("HOPPER_PENDING_REAP_AFTER", 120*time.Second),
	}
	return cfg, nil
}

func getEnv(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}

// getEnvDuration reads a duration in whole seconds (e.g. "120"), falling back on
// an unset or unparseable value. Seconds keep the env var simple to set by hand.
func getEnvDuration(key string, fallback time.Duration) time.Duration {
	if val := os.Getenv(key); val != "" {
		if secs, err := strconv.Atoi(val); err == nil && secs >= 0 {
			return time.Duration(secs) * time.Second
		}
	}
	return fallback
}
