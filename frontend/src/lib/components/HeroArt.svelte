<script lang="ts">
  import { cn } from '$lib/utils';

  let { class: className }: { class?: string } = $props();
</script>

<!-- Decorative hop-trajectory art: warm sunrise arcs + a dotted bounce path.
     Purely aesthetic — hidden from assistive tech. -->
<svg
  viewBox="0 0 420 160"
  fill="none"
  aria-hidden="true"
  class={cn('pointer-events-none select-none', className)}
>
  <defs>
    <linearGradient id="ha-warm" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#f59e0b" stop-opacity="0.9" />
      <stop offset="0.55" stop-color="#fb923c" stop-opacity="0.55" />
      <stop offset="1" stop-color="#8b5cf6" stop-opacity="0.35" />
    </linearGradient>
    <linearGradient id="ha-cool" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#8b5cf6" stop-opacity="0.5" />
      <stop offset="1" stop-color="#f59e0b" stop-opacity="0.25" />
    </linearGradient>
    <radialGradient id="ha-sun" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#fbbf24" stop-opacity="0.9" />
      <stop offset="0.7" stop-color="#f59e0b" stop-opacity="0.35" />
      <stop offset="1" stop-color="#f59e0b" stop-opacity="0" />
    </radialGradient>
  </defs>

  <!-- sun -->
  <circle cx="332" cy="78" r="46" fill="url(#ha-sun)" />
  <circle cx="332" cy="78" r="17" fill="#fbbf24" opacity="0.85" />

  <!-- horizon arcs -->
  <path d="M210 132 A 122 122 0 0 1 420 96" stroke="url(#ha-warm)" stroke-width="2.5" stroke-linecap="round" />
  <path d="M232 148 A 150 150 0 0 1 420 124" stroke="url(#ha-warm)" stroke-width="1.5" stroke-linecap="round" opacity="0.6" />
  <path d="M256 160 A 190 190 0 0 1 420 148" stroke="url(#ha-warm)" stroke-width="1" stroke-linecap="round" opacity="0.35" />

  <!-- dotted hop trajectory (rabbit bounces) -->
  <path
    d="M8 128 Q 48 66 88 122 Q 120 78 152 120 Q 178 92 202 118"
    stroke="url(#ha-cool)"
    stroke-width="2"
    stroke-linecap="round"
    stroke-dasharray="1 9"
  />
  <!-- landing points -->
  {#each [[8, 128], [88, 122], [152, 120], [202, 118]] as [x, y]}
    <circle cx={x} cy={y} r="3" fill="#8b5cf6" opacity="0.55" />
  {/each}
  <!-- apex sparks -->
  {#each [[48, 76, '#f59e0b'], [120, 88, '#fb923c'], [178, 98, '#fbbf24']] as [x, y, c]}
    <circle cx={x} cy={y} r="2" fill={String(c)} />
  {/each}
</svg>
