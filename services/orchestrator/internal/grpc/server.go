package grpc

import (
	"fmt"
	"net"

	"github.com/nats-io/nats.go"
	"go.uber.org/zap"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"

	"github.com/hopper/orchestrator/internal/config"
	"github.com/hopper/orchestrator/internal/pod"
	"github.com/hopper/orchestrator/internal/billing"
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

	// TODO: Register PodOrchestrator and BillingService when proto stubs are generated

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
