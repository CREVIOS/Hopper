package billing

type VmPlan struct {
	Name         string
	CreditsPerHr float64
}

// Plans is the built-in fallback pricing. Once plan pricing is admin-configurable
// the gateway supplies the authoritative rate over gRPC; this map is only used
// when that rate is absent (0) — e.g. an older gateway, or a pod created before
// the credits-per-hour annotation existed.
var Plans = map[string]VmPlan{
	"small":  {Name: "Small", CreditsPerHr: 1},
	"medium": {Name: "Medium", CreditsPerHr: 2},
	"large":  {Name: "Large", CreditsPerHr: 4},
}

// ResolveRate returns the credits-per-hour to bill: the gateway-supplied rate
// when set (>0), otherwise the built-in Plans default for the plan name. Returns
// 0 for an unknown plan with no supplied rate, which keeps billing off.
func ResolveRate(supplied float64, plan string) float64 {
	if supplied > 0 {
		return supplied
	}
	if p, ok := Plans[plan]; ok {
		return p.CreditsPerHr
	}
	return 0
}
