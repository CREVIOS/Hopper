package k8s

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeKubeconfig(t *testing.T) string {
	t.Helper()

	dir := t.TempDir()
	kubeconfigPath := filepath.Join(dir, "config")
	kubeconfig := `
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: https://127.0.0.1:6443
  name: local
contexts:
- context:
    cluster: local
    user: local
  name: local
current-context: local
users:
- name: local
  user:
    token: test-token
`
	if err := os.WriteFile(kubeconfigPath, []byte(kubeconfig), 0o600); err != nil {
		t.Fatalf("write kubeconfig: %v", err)
	}
	return kubeconfigPath
}

func TestRestConfigUsesProvidedKubeconfigPath(t *testing.T) {
	kubeconfigPath := writeKubeconfig(t)

	cfg, err := restConfig(kubeconfigPath)
	if err != nil {
		t.Fatalf("restConfig: %v", err)
	}
	if cfg.Host != "https://127.0.0.1:6443" {
		t.Fatalf("cfg.Host = %q", cfg.Host)
	}
}

func TestRestConfigWrapsKubeconfigErrors(t *testing.T) {
	_, err := restConfig("/definitely/missing/kubeconfig")
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), "building kubeconfig") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestClientConstructorsUseResolvedConfig(t *testing.T) {
	kubeconfigPath := writeKubeconfig(t)

	cfg, err := RestConfig(kubeconfigPath)
	if err != nil {
		t.Fatalf("RestConfig: %v", err)
	}
	if cfg.Host != "https://127.0.0.1:6443" {
		t.Fatalf("cfg.Host = %q", cfg.Host)
	}

	clientset, err := NewClientset(kubeconfigPath)
	if err != nil {
		t.Fatalf("NewClientset: %v", err)
	}
	if clientset == nil {
		t.Fatal("clientset is nil")
	}

	metricsClient, err := NewMetricsClientset(kubeconfigPath)
	if err != nil {
		t.Fatalf("NewMetricsClientset: %v", err)
	}
	if metricsClient == nil {
		t.Fatal("metrics clientset is nil")
	}
}
