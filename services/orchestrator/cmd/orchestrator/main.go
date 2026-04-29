package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"go.uber.org/zap"

	"github.com/hopper/orchestrator/internal/config"
	"github.com/hopper/orchestrator/internal/events"
	grpcserver "github.com/hopper/orchestrator/internal/grpc"
	"github.com/hopper/orchestrator/internal/k8s"
)

func main() {
	logger, _ := zap.NewProduction()
	defer logger.Sync()

	cfg, err := config.Load()
	if err != nil {
		logger.Fatal("failed to load config", zap.Error(err))
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Connect to NATS
	nc, err := events.Connect(cfg.NatsURL)
	if err != nil {
		logger.Fatal("failed to connect to NATS", zap.Error(err))
	}
	defer nc.Close()

	// Initialize K8s client
	clientset, err := k8s.NewClientset(cfg.KubeConfig)
	if err != nil {
		logger.Fatal("failed to create k8s client", zap.Error(err))
	}
	k8sPods := k8s.NewPodManager(clientset, cfg.KubeNamespace)
	if metricsClient, err := k8s.NewMetricsClientset(cfg.KubeConfig); err == nil {
		k8sPods.SetMetricsClient(metricsClient)
		logger.Info("metrics-server client initialized")
	} else {
		logger.Warn("metrics-server unavailable; live CPU/RAM will report 0", zap.Error(err))
	}
	logger.Info("k8s client initialized", zap.String("namespace", cfg.KubeNamespace))

	// Start gRPC server
	srv, err := grpcserver.New(cfg, logger, nc, k8sPods)
	if err != nil {
		logger.Fatal("failed to create gRPC server", zap.Error(err))
	}

	// Subscribe to NATS events (billing.exhausted → auto-terminate pods)
	if err := events.SubscribeAll(nc, logger, srv.PodManager(), k8sPods, srv.Ticker()); err != nil {
		logger.Fatal("failed to subscribe to NATS events", zap.Error(err))
	}

	// Start background metrics publisher (publishes to NATS every 5s for all running pods)
	events.StartMetricsPublisher(ctx, nc, logger, srv.PodManager(), k8sPods)

	go func() {
		if err := srv.Start(cfg.GRPCPort); err != nil {
			logger.Fatal("gRPC server failed", zap.Error(err))
		}
	}()

	logger.Info("orchestrator started", zap.String("grpc_port", fmt.Sprintf(":%d", cfg.GRPCPort)))

	// Graceful shutdown
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	select {
	case <-sigCh:
		logger.Info("shutting down")
	case <-ctx.Done():
	}

	srv.Stop()
}
