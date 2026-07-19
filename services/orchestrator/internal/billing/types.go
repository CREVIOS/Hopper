package billing

type VmPlan struct {
	Name         string
	CreditsPerHr float64
}

var Plans = map[string]VmPlan{
	"small":  {Name: "Small", CreditsPerHr: 1},
	"medium": {Name: "Medium", CreditsPerHr: 2},
	"large":  {Name: "Large", CreditsPerHr: 4},
}

// ResolveRate picks the billing rate (credits/hour) for a pod.
//
// A positive supplied rate — the plan's credits_per_hour, set by the gateway
// from the admin-managed DB plan catalogue — always wins, so pricing changes
// made in the admin UI reach real billing. It falls back to the built-in
// Plans map only when no rate was supplied (older gateways, or pods created
// before the rate was plumbed through), and finally to 0 for a plan the map
// doesn't know — which makes the ticker a no-op rather than billing a guess.
func ResolveRate(supplied float64, plan string) float64 {
	if supplied > 0 {
		return supplied
	}
	if p, ok := Plans[plan]; ok {
		return p.CreditsPerHr
	}
	return 0
}
