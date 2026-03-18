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
