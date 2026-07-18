<script lang="ts">
  import { Activity } from 'lucide-svelte';
  import type { VmMetrics } from '$lib/types';
  import { Card } from '$lib/ui';
  import { cn, formatBytes } from '$lib/utils';

  let { metrics }: { metrics: VmMetrics | null } = $props();

  const memPercent = $derived(
    metrics && metrics.memory_limit_bytes > 0
      ? (metrics.memory_used_bytes / metrics.memory_limit_bytes) * 100
      : 0
  );

  // Threshold-driven accent — modest, on-theme, only to signal load.
  function tone(pct: number): { ring: string; label: string } {
    if (pct > 80) return { ring: 'text-destructive', label: 'High' };
    if (pct > 60) return { ring: 'text-warning', label: 'Elevated' };
    return { ring: 'text-primary', label: 'Healthy' };
  }

  const R = 52;
  const C = 2 * Math.PI * R;
  const dash = (pct: number) => C * (1 - Math.min(100, Math.max(0, pct)) / 100);

  const cpuTone = $derived(tone(metrics?.cpu_percent ?? 0));
  const memTone = $derived(tone(memPercent));
</script>

{#snippet gauge(pct: number, ringClass: string, label: string, sub: string)}
  <div class="flex flex-col items-center gap-3">
    <div class="relative size-28">
      <svg viewBox="0 0 120 120" class="size-full -rotate-90">
        <circle cx="60" cy="60" r={R} fill="none" stroke="currentColor" stroke-width="9" class="text-muted-foreground/15" />
        <circle
          cx="60"
          cy="60"
          r={R}
          fill="none"
          stroke="currentColor"
          stroke-width="9"
          stroke-linecap="round"
          stroke-dasharray={C}
          stroke-dashoffset={dash(pct)}
          class={cn('transition-all duration-700 ease-out', ringClass)}
        />
      </svg>
      <div class="absolute inset-0 flex items-center justify-center">
        <span class="text-2xl font-bold tabular-nums tracking-tight">{pct.toFixed(0)}%</span>
      </div>
    </div>
    <div class="text-center">
      <div class="text-sm font-medium">{label}</div>
      {#if sub}<div class="text-xs text-muted-foreground">{sub}</div>{/if}
    </div>
  </div>
{/snippet}

<Card class="overflow-hidden">
  <div class="flex items-center gap-2.5 px-5 pb-4 pt-5">
    <span class="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
      <Activity class="size-4" />
    </span>
    <h3 class="text-sm font-semibold">Live Metrics</h3>
    {#if metrics}
      <span class="ml-auto inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <span class="size-1.5 animate-pulse rounded-full bg-success"></span>
        Streaming
      </span>
    {/if}
  </div>

  {#if metrics}
    <div class="grid grid-cols-2 gap-4 border-t border-border/60 px-5 py-6">
      {@render gauge(metrics.cpu_percent, cpuTone.ring, 'CPU', cpuTone.label)}
      {@render gauge(
        memPercent,
        memTone.ring,
        'Memory',
        `${formatBytes(metrics.memory_used_bytes)} / ${formatBytes(metrics.memory_limit_bytes)}`
      )}
    </div>
  {:else}
    <div class="flex items-center gap-3 border-t border-border/60 px-5 py-8 text-sm text-muted-foreground">
      <span class="size-2 animate-pulse rounded-full bg-muted-foreground/40"></span>
      Waiting for metrics…
    </div>
  {/if}
</Card>
