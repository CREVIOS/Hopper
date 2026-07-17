package pod

import (
	"fmt"
	"sync"
	"time"
)

type Manager struct {
	mu   sync.RWMutex
	pods map[string]*Pod
}

func NewManager() *Manager {
	return &Manager{
		pods: make(map[string]*Pod),
	}
}

type CreateOpts struct {
	ID        string
	UserID    string
	Plan      string
	Image     string
	CPU       string
	Memory    string
	Namespace string
	PodName   string
}

func (m *Manager) Create(opts CreateOpts) (*Pod, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, exists := m.pods[opts.ID]; exists {
		return m.pods[opts.ID], nil // Idempotent
	}

	p := &Pod{
		ID:        opts.ID,
		UserID:    opts.UserID,
		State:     StatePending,
		Plan:      opts.Plan,
		Image:     opts.Image,
		CPU:       opts.CPU,
		Memory:    opts.Memory,
		Namespace: opts.Namespace,
		PodName:   opts.PodName,
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	m.pods[opts.ID] = p
	return p, nil
}

func (m *Manager) Transition(id string, newState State) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	p, ok := m.pods[id]
	if !ok {
		return fmt.Errorf("pod %s not found", id)
	}

	allowed, exists := ValidTransitions[p.State]
	if !exists {
		return fmt.Errorf("no transitions from state %s", p.State)
	}

	for _, s := range allowed {
		if s == newState {
			p.State = newState
			p.UpdatedAt = time.Now()
			return nil
		}
	}

	return fmt.Errorf("invalid transition from %s to %s", p.State, newState)
}

func (m *Manager) Get(id string) (*Pod, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	p, ok := m.pods[id]
	return p, ok
}

// GetByPodName finds a pod by its Kubernetes pod name. Needed because the
// manager key differs by registration era: CreatePod keys fresh pods by the
// orchestrator-internal name (vm-<unixnano>) while Reconcile keys recovered
// pods by the API UUID label — the K8s watcher only has the K8s name + labels
// and must be able to find either. O(n) scan; n is small (VMs on one node).
func (m *Manager) GetByPodName(podName string) (*Pod, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, p := range m.pods {
		if p.PodName == podName {
			return p, true
		}
	}
	return nil, false
}

// SetState force-sets the state without transition validation (for reconciliation only).
func (m *Manager) SetState(id string, state State) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if p, ok := m.pods[id]; ok {
		p.State = state
	}
}

func (m *Manager) SetSshPort(id string, port int32) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if p, ok := m.pods[id]; ok {
		p.SshPort = port
	}
}

// ListRunning returns all pods in the running state.
func (m *Manager) ListRunning() []*Pod {
	m.mu.RLock()
	defer m.mu.RUnlock()
	var result []*Pod
	for _, p := range m.pods {
		if p.State == StateRunning {
			result = append(result, p)
		}
	}
	return result
}

func (m *Manager) SetPorts(id string, sshPort, vscodePort int32) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if p, ok := m.pods[id]; ok {
		p.SshPort = sshPort
		p.VSCodePort = vscodePort
	}
}

func (m *Manager) SetSshPassword(id string, password string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if p, ok := m.pods[id]; ok {
		p.SshPassword = password
	}
}

// SetNodeName records which node the scheduler placed the pod on. Empty until
// the pod is scheduled; the K8s watcher fills it in once p.Spec.NodeName is set.
func (m *Manager) SetNodeName(id string, nodeName string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if p, ok := m.pods[id]; ok {
		p.NodeName = nodeName
	}
}
