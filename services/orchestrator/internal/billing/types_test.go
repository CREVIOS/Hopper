package billing

import "testing"

func TestResolveRate(t *testing.T) {
	tests := []struct {
		name     string
		supplied float64
		plan     string
		want     float64
	}{
		{
			name:     "supplied rate wins over the plan map",
			supplied: 2.5, // admin-set DB price that differs from the hardcoded map
			plan:     "small",
			want:     2.5,
		},
		{
			name:     "supplied rate wins even for an unknown plan",
			supplied: 7,
			plan:     "gpu-xl", // not in the built-in map
			want:     7,
		},
		{
			name:     "zero supplied falls back to the built-in plan map",
			supplied: 0,
			plan:     "medium",
			want:     2,
		},
		{
			name:     "negative supplied is ignored, falls back to the map",
			supplied: -1,
			plan:     "large",
			want:     4,
		},
		{
			name:     "zero supplied and unknown plan yields zero (billing no-op)",
			supplied: 0,
			plan:     "mystery",
			want:     0,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := ResolveRate(tt.supplied, tt.plan); got != tt.want {
				t.Errorf("ResolveRate(%v, %q) = %v, want %v", tt.supplied, tt.plan, got, tt.want)
			}
		})
	}
}
