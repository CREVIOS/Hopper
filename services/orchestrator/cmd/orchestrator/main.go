package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"

	"go.uber.org/zap"

	"github.com/hopper/orchestrator/internal/config"
	"github.com/hopper/orchestrator/internal/events"
	grpcserver "github.com/hopper/orchestrator/internal/grpc"
	"github.com/hopper/orchestrator/internal/k8s"
	"github.com/hopper/orchestrator/internal/leader"
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

	// The singleton workload: exactly one orchestrator instance may run this
	// at a time — billing tickers double-charge and the exhaustion handler
	// double-kills if two instances run them concurrently.
	//
	// It rebuilds in-memory pod state from existing K8s pods, then keeps it
	// synced via a continuous watch. Without the reconcile the in-memory pod
	// map starts empty on every restart, so live metrics and per-pod billing
	// silently stop for all pre-existing VMs until each one is recreated.
	runSingletonWork := func(ctx context.Context) {
		// billing.exhausted → auto-terminate pods
		if err := events.SubscribeAll(nc, logger, srv.PodManager(), k8sPods, srv.Ticker()); err != nil {
			logger.Fatal("failed to subscribe to NATS events", zap.Error(err))
		}

		watcher := k8s.NewPodWatcher(clientset, cfg.KubeNamespace, logger, func(subject string, data any) error {
			return events.Publish(nc, subject, data)
		})
		watcher.Reconcile(ctx, srv.PodManager(), srv.Ticker())
		go watcher.Watch(ctx, srv.PodManager(), srv.Ticker())

		// Background metrics publisher (publishes to NATS every 5s for all running pods)
		events.StartMetricsPublisher(ctx, nc, logger, srv.PodManager(), k8sPods)
	}

	var shuttingDown atomic.Bool

	if cfg.LeaderElection {
		// Leader election via a K8s Lease: the gRPC server answers on every
		// instance immediately, but tickers/watcher/subscriptions wait for
		// leadership. Losing the lease mid-run is unrecoverable in-process
		// (the tickers can't be safely un-started) — exit and let K8s
		// restart us into a clean follower.
		go leader.Run(ctx, clientset, cfg.KubeNamespace, logger, leader.Callbacks{
			OnStartedLeading: runSingletonWork,
			OnStoppedLeading: func() {
				if shuttingDown.Load() {
					logger.Info("released leadership on shutdown")
					return
				}
				logger.Fatal("lost leadership unexpectedly — exiting so the new leader owns billing")
			},
		})
	} else {
		runSingletonWork(ctx)
	}

	go func() {
		if err := srv.Start(cfg.GRPCPort); err != nil {
			logger.Fatal("gRPC server failed", zap.Error(err))
		}
	}()

	// Drive the gRPC health status from real dependency checks so K8s probes
	// (and the gateway's /readyz) see NATS or K8s API outages. The gRPC
	// server itself serving is not enough — a deaf orchestrator can't bill
	// or terminate anything.
	go func() {
		ticker := time.NewTicker(10 * time.Second)
		defer ticker.Stop()
		check := func() {
			ok := nc.IsConnected()
			if ok {
				cctx, cancel := context.WithTimeout(ctx, 5*time.Second)
				_, err := clientset.Discovery().RESTClient().Get().AbsPath("/version").DoRaw(cctx)
				cancel()
				ok = err == nil
			}
			srv.SetServing(ok)
		}
		check()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				check()
			}
		}
	}()

	logger.Info("orchestrator started",
		zap.String("grpc_port", fmt.Sprintf(":%d", cfg.GRPCPort)),
		zap.Bool("leader_election", cfg.LeaderElection),
	)

	// Graceful shutdown
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	select {
	case <-sigCh:
		shuttingDown.Store(true)
		logger.Info("shutting down")
	case <-ctx.Done():
	}

	// Release the leadership lease (ReleaseOnCancel) before stopping gRPC so
	// the replacement instance can take over without waiting out the lease.
	cancel()
	srv.Stop()
}
