package leader

import (
	"context"
	"os"
	"time"

	"go.uber.org/zap"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/leaderelection"
	"k8s.io/client-go/tools/leaderelection/resourcelock"
)

type Callbacks struct {
	OnStartedLeading func(ctx context.Context)
	OnStoppedLeading func()
}

// Run starts leader election. OnStartedLeading is called when this instance
// becomes the leader. OnStoppedLeading is called when leadership is lost.
// This function blocks until the context is cancelled.
func Run(ctx context.Context, client *kubernetes.Clientset, namespace string, logger *zap.Logger, cb Callbacks) {
	id := os.Getenv("POD_NAME")
	if id == "" {
		id = "orchestrator-" + time.Now().Format("20060102150405")
	}

	lock := &resourcelock.LeaseLock{
		LeaseMeta: metav1.ObjectMeta{
			Name:      "orchestrator-leader",
			Namespace: namespace,
		},
		Client: client.CoordinationV1(),
		LockConfig: resourcelock.ResourceLockConfig{
			Identity: id,
		},
	}

	leaderelection.RunOrDie(ctx, leaderelection.LeaderElectionConfig{
		Lock:            lock,
		LeaseDuration:   15 * time.Second,
		RenewDeadline:   10 * time.Second,
		RetryPeriod:     2 * time.Second,
		ReleaseOnCancel: true,
		Callbacks: leaderelection.LeaderCallbacks{
			OnStartedLeading: func(ctx context.Context) {
				logger.Info("became leader", zap.String("id", id))
				cb.OnStartedLeading(ctx)
			},
			OnStoppedLeading: func() {
				logger.Warn("lost leadership", zap.String("id", id))
				cb.OnStoppedLeading()
			},
			OnNewLeader: func(identity string) {
				if identity != id {
					logger.Info("new leader elected", zap.String("leader", identity))
				}
			},
		},
	})
}
