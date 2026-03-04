package pod

import "time"

type State string

const (
	StatePending    State = "pending"
	StateCreating   State = "creating"
	StateRunning    State = "running"
	StateStopping   State = "stopping"
	StateTerminated State = "terminated"
	StateFailed     State = "failed"
)

// ValidTransitions defines the pod lifecycle state machine.
var ValidTransitions = map[State][]State{
	StatePending:  {StateCreating, StateFailed},
	StateCreating: {StateRunning, StateFailed},
	StateRunning:  {StateStopping, StateFailed},
	StateStopping: {StateTerminated, StateFailed},
}

type Pod struct {
	ID        string
	UserID    string
	State     State
	GpuTier   string
	Image     string
	NodeName  string
	Namespace string
	CreatedAt time.Time
	UpdatedAt time.Time
}
