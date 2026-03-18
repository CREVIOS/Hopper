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
