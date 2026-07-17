package grpc

import (
	"context"
	"fmt"
	"time"

	"go.uber.org/zap"
	"google.golang.org/protobuf/types/known/timestamppb"

	"github.com/hopper/orchestrator/internal/events"
	"github.com/hopper/orchestrator/internal/k8s"
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
		Id:          p.ID,
		UserId:      p.UserID,
		State:       podToProtoState(p.State),
		Plan:        p.Plan,
		NodeName:    p.NodeName,
		Namespace:   p.Namespace,
		SshPort:     p.SshPort,
		VscodePort:  p.VSCodePort,
		SshPassword: p.SshPassword,
		Cpu:         p.CPU,
		Memory:      p.Memory,
		CreatedAt:   timestamppb.New(p.CreatedAt),
		UpdatedAt:   timestamppb.New(p.UpdatedAt),
	}
}

func (s *PodOrchestratorService) CreatePod(ctx context.Context, req *podv1.CreatePodRequest) (*podv1.PodStatus, error) {
	podName := fmt.Sprintf("vm-%d", time.Now().UnixNano())

	// Optional network isolation group (HOP-19 18.3), carried in the labels
	// map. Validated here because label values flow into K8s objects.
	networkGroup := req.Labels[k8s.NetworkGroupLabel]
	if networkGroup != "" && !k8s.ValidNetworkGroup(networkGroup) {
		return nil, fmt.Errorf("invalid network group %q", networkGroup)
	}

	s.server.logger.Info("CreatePod",
		zap.String("user_id", req.UserId),
		zap.String("plan", req.Plan),
		zap.String("image", req.Image),
		zap.String("cpu", req.Cpu),
		zap.String("memory", req.Memory),
		zap.String("network_group", networkGroup),
	)

	// 1. Register in the in-memory state machine
	p, err := s.server.podManager.Create(pod.CreateOpts{
		ID:        podName,
		UserID:    req.UserId,
		Plan:      req.Plan,
		Image:     req.Image,
		CPU:       req.Cpu,
		Memory:    req.Memory,
		Namespace: "hopper",
		PodName:   podName,
	})
	if err != nil {
		return nil, fmt.Errorf("registering pod: %w", err)
	}

	// 2. Transition to creating
	if err := s.server.podManager.Transition(p.ID, pod.StateCreating); err != nil {
		return nil, fmt.Errorf("transitioning to creating: %w", err)
	}

	// 3. Create the actual K8s pod + SSH + VS Code services.
	// PodID flows from the API (req.PodId) so the K8s label and the
	// code-server --base-path use the same identifier external URLs use.
	// Fall back to podName if the caller didn't pass one (e.g. older clients).
	apiPodID := req.PodId
	if apiPodID == "" {
		apiPodID = podName
	}
	ports, err := s.server.k8sPods.CreatePod(ctx, k8s.CreatePodOpts{
		PodName:      podName,
		PodID:        apiPodID,
		UserID:       req.UserId,
		Plan:         req.Plan,
		Image:        req.Image,
		CPU:          req.Cpu,
		Memory:       req.Memory,
		NetworkGroup: networkGroup,
	})
	if err != nil {
		_ = s.server.podManager.Transition(p.ID, pod.StateFailed)
		_ = events.Publish(s.server.nc, events.SubjectPodFailed, map[string]string{
			"pod_id": p.ID,
			// The gateway's DB row is keyed by the API UUID, not our
			// internal name — include it so consumers can find the session.
			"api_pod_id": apiPodID,
			"user_id":    req.UserId,
			"error":      err.Error(),
		})
		return nil, fmt.Errorf("creating k8s pod: %w", err)
	}

	// 4. Record ports + per-pod ssh password. The pod stays `creating` here:
	// CreatePod returns as soon as the API server accepts the object, which is
	// long before the scheduler places it and the kubelet starts it — and on a
	// multi-node cluster it may never be placed at all (no node with room).
	// The K8s watcher owns the transition to running, and starts billing, when
	// the container is actually observed Running.
	s.server.podManager.SetPorts(p.ID, ports.SSHPort, ports.VSCodePort)
	s.server.podManager.SetSshPassword(p.ID, ports.SSHPassword)

	// 5. Publish event
	_ = events.Publish(s.server.nc, events.SubjectPodCreated, map[string]interface{}{
		"pod_id":      p.ID,
		"api_pod_id":  apiPodID,
		"user_id":     req.UserId,
		"ssh_port":    ports.SSHPort,
		"vscode_port": ports.VSCodePort,
		"plan":        req.Plan,
	})

	// Refresh the pod to include ssh_port
	p, _ = s.server.podManager.Get(p.ID)
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

	p, ok := s.server.podManager.Get(req.Id)
	if !ok {
		return &podv1.TerminateResponse{Success: false, Message: "pod not found"}, nil
	}

	if err := s.server.podManager.Transition(req.Id, pod.StateStopping); err != nil {
		return &podv1.TerminateResponse{Success: false, Message: err.Error()}, nil
	}

	// Stop billing
	s.server.ticker.Stop(req.Id)

	// Delete the actual K8s pod + service
	if err := s.server.k8sPods.DeletePod(ctx, p.PodName); err != nil {
		s.server.logger.Warn("failed to delete k8s pod", zap.Error(err))
	}

	// Transition to terminated
	_ = s.server.podManager.Transition(req.Id, pod.StateTerminated)

	// Publish event
	_ = events.Publish(s.server.nc, events.SubjectPodStopped, map[string]string{
		"pod_id":  req.Id,
		"user_id": p.UserID,
	})

	return &podv1.TerminateResponse{Success: true, Message: "pod terminated"}, nil
}

func (s *PodOrchestratorService) StreamMetrics(req *podv1.PodId, stream podv1.PodOrchestrator_StreamMetricsServer) error {
	p, ok := s.server.podManager.Get(req.Id)
	if !ok {
		return fmt.Errorf("pod %s not found", req.Id)
	}

	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-stream.Context().Done():
			return nil
		case <-ticker.C:
			// Fetch real metrics from K8s
			podMetrics, err := s.server.k8sPods.GetPodMetrics(stream.Context(), p.PodName)
			if err != nil {
				s.server.logger.Debug("metrics fetch failed", zap.Error(err))
				continue
			}

			metrics := &podv1.VmMetrics{
				PodId:            req.Id,
				CpuPercent:       float64(podMetrics.CPUNanoCores) / 1e9 * 100,
				MemoryUsedBytes:  podMetrics.MemoryBytes,
				MemoryLimitBytes: podMetrics.MemoryLimitBytes,
				Timestamp:        timestamppb.Now(),
			}

			// Send via gRPC stream
			if err := stream.Send(metrics); err != nil {
				return err
			}

			// Also publish to NATS so the gateway SSE endpoint can use it
			_ = events.Publish(s.server.nc, fmt.Sprintf("metrics.%s", req.Id), map[string]interface{}{
				"pod_id":             req.Id,
				"cpu_percent":        metrics.CpuPercent,
				"memory_used_bytes":  metrics.MemoryUsedBytes,
				"memory_limit_bytes": metrics.MemoryLimitBytes,
			})
		}
	}
}

func (s *PodOrchestratorService) WatchPodStatus(req *podv1.PodId, stream podv1.PodOrchestrator_WatchPodStatusServer) error {
	p, ok := s.server.podManager.Get(req.Id)
	if !ok {
		return fmt.Errorf("pod %s not found", req.Id)
	}
	return stream.Send(podToProto(p))
}

func (s *PodOrchestratorService) ListNodes(ctx context.Context, req *podv1.ListNodesRequest) (*podv1.ListNodesResponse, error) {
	nodes, err := s.server.k8sPods.ListNodes(ctx)
	if err != nil {
		return nil, fmt.Errorf("listing nodes: %w", err)
	}

	var protoNodes []*podv1.NodeInfo
	for _, n := range nodes {
		protoNodes = append(protoNodes, &podv1.NodeInfo{
			Name:              n.Name,
			CpuCapacity:       n.CPUCapacity,
			MemoryCapacity:    n.MemoryCapacity,
			CpuAllocatable:    n.CPUAllocatable,
			MemoryAllocatable: n.MemoryAllocatable,
			PodCount:          int32(n.PodCount),
			Ready:             n.Ready,
		})
	}

	return &podv1.ListNodesResponse{Nodes: protoNodes}, nil
}
