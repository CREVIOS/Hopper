<script lang="ts">
  // Lightweight SVG donut / ring chart. Pass `segments` for a multi-slice donut,
  // or a single `percent` for a gauge ring. Center label is HTML-overlaid so it
  // uses the app font + theme tokens cleanly.
  let {
    segments = [],
    percent = null,
    size = 148,
    thickness = 16,
    trackColor = 'hsl(var(--muted))',
    accent = 'hsl(var(--primary))',
    centerValue,
    centerLabel
  }: {
    segments?: { label: string; value: number; color: string }[];
    percent?: number | null;
    size?: number;
    thickness?: number;
    trackColor?: string;
    accent?: string;
    centerValue?: string;
    centerLabel?: string;
  } = $props();

  const r = $derived((size - thickness) / 2);
  const circ = $derived(2 * Math.PI * r);

  // Build cumulative arcs from segments (or a single arc from `percent`).
  const arcs = $derived.by(() => {
    if (percent != null) {
      return [{ len: (Math.max(0, Math.min(100, percent)) / 100) * circ, off: 0, color: accent }];
    }
    const total = segments.reduce((s, x) => s + x.value, 0) || 1;
    let off = 0;
    return segments.map((s) => {
      const len = (s.value / total) * circ;
      const a = { len, off, color: s.color };
      off += len;
      return a;
    });
  });
</script>

<div class="relative shrink-0" style="width:{size}px;height:{size}px">
  <svg width={size} height={size} viewBox="0 0 {size} {size}">
    <g transform="rotate(-90 {size / 2} {size / 2})">
      <circle cx={size / 2} cy={size / 2} {r} fill="none" stroke={trackColor} stroke-width={thickness} />
      {#each arcs as a}
        <circle
          cx={size / 2}
          cy={size / 2}
          {r}
          fill="none"
          stroke={a.color}
          stroke-width={thickness}
          stroke-dasharray="{a.len} {circ}"
          stroke-dashoffset={-a.off}
          stroke-linecap="round"
        />
      {/each}
    </g>
  </svg>
  {#if centerValue}
    <div class="absolute inset-0 flex flex-col items-center justify-center">
      <span class="text-2xl font-bold tracking-tight text-foreground">{centerValue}</span>
      {#if centerLabel}<span class="text-xs text-muted-foreground">{centerLabel}</span>{/if}
    </div>
  {/if}
</div>
