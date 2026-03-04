package billing

type GpuTier struct {
	Name         string
	CreditsPerHr float64
}

var Tiers = map[string]GpuTier{
	"premium":   {Name: "Premium", CreditsPerHr: 15},
	"standard":  {Name: "Standard", CreditsPerHr: 10},
	"budget":    {Name: "Budget", CreditsPerHr: 5},
	"scavenger": {Name: "Scavenger", CreditsPerHr: 0},
}
