package k8s

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRestConfigUsesProvidedKubeconfigPath(t *testing.T) {
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
