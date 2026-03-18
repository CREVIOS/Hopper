package k8s

import (
	"fmt"
	"os"
	"path/filepath"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

// NewClientset creates a Kubernetes clientset.
// It tries in-cluster config first (when running inside a pod),
// then falls back to KUBECONFIG or ~/.kube/config for local dev.
func NewClientset(kubeconfigPath string) (*kubernetes.Clientset, error) {
	// Try in-cluster first (production)
	cfg, err := rest.InClusterConfig()
	if err == nil {
		return kubernetes.NewForConfig(cfg)
	}

	// Fall back to kubeconfig (local dev)
	if kubeconfigPath == "" {
		home, _ := os.UserHomeDir()
		kubeconfigPath = filepath.Join(home, ".kube", "config")
	}

	cfg, err = clientcmd.BuildConfigFromFlags("", kubeconfigPath)
	if err != nil {
		return nil, fmt.Errorf("building kubeconfig: %w", err)
	}

	return kubernetes.NewForConfig(cfg)
}
