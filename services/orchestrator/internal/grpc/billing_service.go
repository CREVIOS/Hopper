package grpc

import (
	"context"

	"go.uber.org/zap"
	"google.golang.org/protobuf/types/known/timestamppb"

	billingv1 "github.com/hopper/orchestrator/api/proto/hopper/billing/v1"
)

type BillingServiceImpl struct {
	billingv1.UnimplementedBillingServiceServer
	server *Server
}

func NewBillingServiceImpl(srv *Server) *BillingServiceImpl {
	return &BillingServiceImpl{server: srv}
}

func (s *BillingServiceImpl) GetBalance(ctx context.Context, req *billingv1.AccountId) (*billingv1.BalanceResponse, error) {
	s.server.logger.Info("GetBalance", zap.String("account_id", req.Id))
	// Placeholder: will call API gateway for real balance
	return &billingv1.BalanceResponse{
		AccountId: req.Id,
		Balance:   0.0,
		AsOf:      timestamppb.Now(),
	}, nil
}

func (s *BillingServiceImpl) DeductCredits(ctx context.Context, req *billingv1.DeductRequest) (*billingv1.DeductResponse, error) {
	s.server.logger.Info("DeductCredits",
		zap.String("account_id", req.AccountId),
		zap.Float64("amount", req.Amount),
		zap.String("reason", req.Reason),
	)
	// Placeholder: will call API gateway for real deduction
	return &billingv1.DeductResponse{
		Success:          true,
		RemainingBalance: 0.0,
		Message:          "deducted (placeholder)",
	}, nil
}

func (s *BillingServiceImpl) StreamUsage(req *billingv1.AccountId, stream billingv1.BillingService_StreamUsageServer) error {
	// Placeholder: no-op for now
	s.server.logger.Info("StreamUsage", zap.String("account_id", req.Id))
	<-stream.Context().Done()
	return nil
}
