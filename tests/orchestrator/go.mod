module github.com/hopper/orchestrator/tests

go 1.23

require (
	github.com/hopper/orchestrator v0.0.0
	go.uber.org/zap v1.27.0
)

require go.uber.org/multierr v1.10.0 // indirect

replace github.com/hopper/orchestrator => ../../services/orchestrator
