package k8s

import (
	"fmt"
	"os"
	"path/filepath"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	metricsv "k8s.io/metrics/pkg/client/clientset/versioned"
)

// restConfig resolves the K8s REST config: in-cluster first, then KUBECONFIG.
func restConfig(kubeconfigPath string) (*rest.Config, error) {
	cfg, err := rest.InClusterConfig()
	if err == nil {
		return cfg, nil
	}

	if kubeconfigPath == "" {
		home, _ := os.UserHomeDir()
		kubeconfigPath = filepath.Join(home, ".kube", "config")
	}

	cfg, err = clientcmd.BuildConfigFromFlags("", kubeconfigPath)
	if err != nil {
		return nil, fmt.Errorf("building kubeconfig: %w", err)
	}
	return cfg, nil
}

// NewClientset creates a Kubernetes clientset.
func NewClientset(kubeconfigPath string) (*kubernetes.Clientset, error) {
	cfg, err := restConfig(kubeconfigPath)
	if err != nil {
		return nil, err
	}
	return kubernetes.NewForConfig(cfg)
}

// NewMetricsClientset creates a metrics-server clientset for querying pod CPU/memory.
func NewMetricsClientset(kubeconfigPath string) (*metricsv.Clientset, error) {
	cfg, err := restConfig(kubeconfigPath)
	if err != nil {
		return nil, err
	}
	return metricsv.NewForConfig(cfg)
}

// RestConfig exposes the resolved config for use by remotecommand (exec).
func RestConfig(kubeconfigPath string) (*rest.Config, error) {
	return restConfig(kubeconfigPath)
}
