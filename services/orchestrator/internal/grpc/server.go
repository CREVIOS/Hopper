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
	"github.com/hopper/orchestrator/internal/pod"
)

type Server struct {
	grpcServer *grpc.Server
	podManager *pod.Manager
	ticker     *billing.Ticker
	logger     *zap.Logger
	nc         *nats.Conn
}

func New(cfg *config.Config, logger *zap.Logger, nc *nats.Conn) (*Server, error) {
	srv := &Server{
		grpcServer: grpc.NewServer(),
		podManager: pod.NewManager(),
		ticker:     billing.NewTicker(logger),
		logger:     logger,
		nc:         nc,
	}

	// Register health service
	healthSrv := health.NewServer()
	healthpb.RegisterHealthServer(srv.grpcServer, healthSrv)

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
