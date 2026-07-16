package grpc

import (
	"fmt"
	"net"

	"github.com/nats-io/nats.go"
	"go.uber.org/zap"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"

	billingv1 "github.com/hopper/orchestrator/api/proto/hopper/billing/v1"
	podv1 "github.com/hopper/orchestrator/api/proto/hopper/pod/v1"
	"github.com/hopper/orchestrator/internal/billing"
	"github.com/hopper/orchestrator/internal/config"
	"github.com/hopper/orchestrator/internal/k8s"
	"github.com/hopper/orchestrator/internal/pod"
)

type Server struct {
	grpcServer *grpc.Server
	podManager *pod.Manager
	k8sPods    *k8s.PodManager
	ticker     *billing.Ticker
	logger     *zap.Logger
	nc         *nats.Conn
	healthSrv  *health.Server
}

func New(cfg *config.Config, logger *zap.Logger, nc *nats.Conn, k8sPods *k8s.PodManager) (*Server, error) {
	srv := &Server{
		grpcServer: grpc.NewServer(),
		podManager: pod.NewManager(),
		k8sPods:    k8sPods,
		ticker:     billing.NewTicker(logger),
		logger:     logger,
		nc:         nc,
	}

	// Register health service. The default ("") status is driven by the
	// dependency checker in main (NATS + K8s API reachability) — the K8s
	// readiness probe and the gateway's /readyz read it. The "liveness"
	// service stays SERVING for as long as the process runs, so the K8s
	// liveness probe never restart-loops the pod over a dependency outage.
	srv.healthSrv = health.NewServer()
	srv.healthSrv.SetServingStatus("liveness", healthpb.HealthCheckResponse_SERVING)
	healthpb.RegisterHealthServer(srv.grpcServer, srv.healthSrv)

	// Register PodOrchestrator service
	podSvc := NewPodOrchestratorService(srv)
	podv1.RegisterPodOrchestratorServer(srv.grpcServer, podSvc)

	// Register BillingService
	billingSvc := NewBillingServiceImpl(srv)
	billingv1.RegisterBillingServiceServer(srv.grpcServer, billingSvc)

	logger.Info("gRPC services registered",
		zap.String("services", "PodOrchestrator, BillingService, Health"),
	)

	return srv, nil
}

func (s *Server) Start(port int) error {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		return fmt.Errorf("failed to listen: %w", err)
	}
	return s.grpcServer.Serve(lis)
}

func (s *Server) Stop() {
	s.grpcServer.GracefulStop()
}

func (s *Server) PodManager() *pod.Manager {
	return s.podManager
}

func (s *Server) Ticker() *billing.Ticker {
	return s.ticker
}

// SetServing flips the gRPC health status for all services ("" = overall).
func (s *Server) SetServing(ok bool) {
	status := healthpb.HealthCheckResponse_SERVING
	if !ok {
		status = healthpb.HealthCheckResponse_NOT_SERVING
	}
	s.healthSrv.SetServingStatus("", status)
}
