package config

import "os"

type Config struct {
	GRPCPort      int
	NatsURL       string
	KubeConfig    string
	KubeNamespace string
	// Namespace Longhorn runs in; where its Node CRs are read for real per-node
	// storage. Defaults to longhorn-system.
	LonghornNamespace string
	// LeaderElection gates the singleton work (billing tickers, pod watcher,
	// exhaustion handling, metrics publishing) behind a K8s Lease so two
	// orchestrator instances — e.g. during a rolling update — never bill the
	// same pods twice. Enabled in the K8s deployment; off for local dev,
	// where there is exactly one instance and no Lease API worth requiring.
	LeaderElection bool
}

func Load() (*Config, error) {
	cfg := &Config{
		GRPCPort:          50051,
		NatsURL:           getEnv("HOPPER_NATS_URL", "nats://localhost:4222"),
		KubeConfig:        getEnv("KUBECONFIG", ""),
		KubeNamespace:     getEnv("KUBERNETES_NAMESPACE", "hopper"),
		LonghornNamespace: getEnv("HOPPER_LONGHORN_NAMESPACE", "longhorn-system"),
		LeaderElection:    getEnv("HOPPER_LEADER_ELECTION", "false") == "true",
	}
	return cfg, nil
}

func getEnv(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}
