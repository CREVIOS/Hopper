package config

import "os"

type Config struct {
	GRPCPort        int
	NatsURL         string
	KubeConfig      string
	KubeNamespace   string
}

func Load() (*Config, error) {
	cfg := &Config{
		GRPCPort:      50051,
		NatsURL:       getEnv("HOPPER_NATS_URL", "nats://localhost:4222"),
		KubeConfig:    getEnv("KUBECONFIG", ""),
		KubeNamespace: getEnv("KUBERNETES_NAMESPACE", "hopper"),
	}
	return cfg, nil
}

func getEnv(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}
