package billing

import "testing"

func TestResolveRate(t *testing.T) {
	cases := []struct {
		name     string
		supplied float64
		plan     string
		want     float64
	}{
		{"supplied rate wins over map", 3.5, "small", 3.5},
		{"supplied rate wins for unknown plan", 7, "custom-gpu", 7},
		{"falls back to map when supplied is zero", 0, "medium", 2},
		{"falls back to map for large", 0, "large", 4},
		{"zero for unknown plan with no supplied rate", 0, "mystery", 0},
		{"negative supplied treated as unset, falls back", -1, "small", 1},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := ResolveRate(tc.supplied, tc.plan); got != tc.want {
				t.Errorf("ResolveRate(%v, %q) = %v, want %v", tc.supplied, tc.plan, got, tc.want)
			}
		})
	}
}
