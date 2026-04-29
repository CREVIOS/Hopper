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
	ID          string
	UserID      string
	State       State
	Plan        string
	Image       string
	CPU         string
	Memory      string
	NodeName    string
	Namespace   string
	PodName     string
	SshPort     int32
	VSCodePort  int32
	SshPassword string
	CreatedAt   time.Time
	UpdatedAt   time.Time
}
