package config

import "os"

type Config struct {
	GRPCPort   int
	NatsURL    string
	KubeConfig string
}

func Load() (*Config, error) {
	cfg := &Config{
		GRPCPort:   50051,
		NatsURL:    getEnv("HOPPER_NATS_URL", "nats://localhost:4222"),
		KubeConfig: getEnv("KUBECONFIG", ""),
	}
	return cfg, nil
}

func getEnv(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}
