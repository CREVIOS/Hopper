package grpc

import (
	"context"
	"fmt"
	"time"

	"go.uber.org/zap"
	"google.golang.org/protobuf/types/known/timestamppb"

	billingpkg "github.com/hopper/orchestrator/internal/billing"
	"github.com/hopper/orchestrator/internal/events"
	"github.com/hopper/orchestrator/internal/pod"

	podv1 "github.com/hopper/orchestrator/api/proto/hopper/pod/v1"
)

type PodOrchestratorService struct {
	podv1.UnimplementedPodOrchestratorServer
	server *Server
}

func NewPodOrchestratorService(srv *Server) *PodOrchestratorService {
	return &PodOrchestratorService{server: srv}
}

func podToProtoState(s pod.State) podv1.PodState {
	switch s {
	case pod.StatePending:
		return podv1.PodState_POD_STATE_PENDING
	case pod.StateCreating:
		return podv1.PodState_POD_STATE_CREATING
	case pod.StateRunning:
		return podv1.PodState_POD_STATE_RUNNING
	case pod.StateStopping:
		return podv1.PodState_POD_STATE_STOPPING
	case pod.StateTerminated:
		return podv1.PodState_POD_STATE_TERMINATED
	case pod.StateFailed:
		return podv1.PodState_POD_STATE_FAILED
	default:
		return podv1.PodState_POD_STATE_UNSPECIFIED
	}
}

func podToProto(p *pod.Pod) *podv1.PodStatus {
	return &podv1.PodStatus{
		Id:        p.ID,
		UserId:    p.UserID,
		State:     podToProtoState(p.State),
		GpuTier:   p.GpuTier,
		NodeName:  p.NodeName,
		Namespace: p.Namespace,
		CreatedAt: timestamppb.New(p.CreatedAt),
		UpdatedAt: timestamppb.New(p.UpdatedAt),
	}
}

func (s *PodOrchestratorService) CreatePod(ctx context.Context, req *podv1.CreatePodRequest) (*podv1.PodStatus, error) {
	s.server.logger.Info("CreatePod",
		zap.String("user_id", req.UserId),
		zap.String("gpu_tier", req.GpuTier),
		zap.String("image", req.Image),
	)

	p, err := s.server.podManager.Create(
		fmt.Sprintf("pod-%d", time.Now().UnixNano()),
		req.UserId,
		req.GpuTier,
		req.Image,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create pod: %w", err)
	}

	// Publish event
	_ = events.Publish(s.server.nc, events.SubjectPodCreated, map[string]string{
		"pod_id":  p.ID,
		"user_id": p.UserID,
	})

	// Start billing ticker
	tier, ok := billingpkg.Tiers[req.GpuTier]
	if ok {
		s.server.ticker.Start(p.ID, tier, func(podID string, amount float64) {
			s.server.logger.Info("billing tick",
				zap.String("pod_id", podID),
				zap.Float64("amount", amount),
			)
			_ = events.Publish(s.server.nc, events.SubjectBillDeduct, map[string]interface{}{
				"pod_id":  podID,
				"amount":  amount,
				"user_id": req.UserId,
			})
		})
	}

	return podToProto(p), nil
}

func (s *PodOrchestratorService) GetPodStatus(ctx context.Context, req *podv1.PodId) (*podv1.PodStatus, error) {
	p, ok := s.server.podManager.Get(req.Id)
	if !ok {
		return nil, fmt.Errorf("pod %s not found", req.Id)
	}
	return podToProto(p), nil
}

func (s *PodOrchestratorService) TerminatePod(ctx context.Context, req *podv1.PodId) (*podv1.TerminateResponse, error) {
	s.server.logger.Info("TerminatePod", zap.String("pod_id", req.Id))

	if err := s.server.podManager.Transition(req.Id, pod.StateStopping); err != nil {
		return &podv1.TerminateResponse{Success: false, Message: err.Error()}, nil
	}

	// Stop billing
	s.server.ticker.Stop(req.Id)

	// Publish event
	_ = events.Publish(s.server.nc, events.SubjectPodStopped, map[string]string{
		"pod_id": req.Id,
	})

	// Transition to terminated
	_ = s.server.podManager.Transition(req.Id, pod.StateTerminated)

	return &podv1.TerminateResponse{Success: true, Message: "pod terminated"}, nil
}

func (s *PodOrchestratorService) StreamMetrics(req *podv1.PodId, stream podv1.PodOrchestrator_StreamMetricsServer) error {
	// Placeholder: send fake metrics every 2 seconds for demonstration
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-stream.Context().Done():
			return nil
		case <-ticker.C:
			metrics := &podv1.GpuMetrics{
				PodId:          req.Id,
				GpuUtilization: 42.0,
				MemoryUsed:     4 * 1024 * 1024 * 1024, // 4GB
				MemoryTotal:    16 * 1024 * 1024 * 1024, // 16GB
				Temperature:    65.0,
				PowerUsage:     150.0,
				Timestamp:      timestamppb.Now(),
			}
			if err := stream.Send(metrics); err != nil {
				return err
			}
		}
	}
}

func (s *PodOrchestratorService) WatchPodStatus(req *podv1.PodId, stream podv1.PodOrchestrator_WatchPodStatusServer) error {
	// Placeholder: send current status once
	p, ok := s.server.podManager.Get(req.Id)
	if !ok {
		return fmt.Errorf("pod %s not found", req.Id)
	}
	return stream.Send(podToProto(p))
}
