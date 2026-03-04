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

func (m *Manager) Create(id, userID, gpuTier, image string) (*Pod, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, exists := m.pods[id]; exists {
		return m.pods[id], nil // Idempotent
	}

	p := &Pod{
		ID:        id,
		UserID:    userID,
		State:     StatePending,
		GpuTier:   gpuTier,
		Image:     image,
		Namespace: fmt.Sprintf("hopper-pod-%s", id),
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	m.pods[id] = p
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
