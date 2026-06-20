<script lang="ts">
  import { Cpu, MemoryStick, Activity } from 'lucide-svelte';
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
  function tone(pct: number): { ring: string; text: string; label: string } {
    if (pct > 80) return { ring: 'text-destructive', text: 'text-destructive', label: 'High' };
    if (pct > 60) return { ring: 'text-warning', text: 'text-warning', label: 'Elevated' };
    return { ring: 'text-primary', text: 'text-primary', label: 'Healthy' };
  }

  const R = 52;
  const C = 2 * Math.PI * R;
  const dash = (pct: number) => C * (1 - Math.min(100, Math.max(0, pct)) / 100);

  const cpuTone = $derived(tone(metrics?.cpu_percent ?? 0));
  const memTone = $derived(tone(memPercent));
</script>

{#snippet gauge(pct: number, ringClass: string, center: string, unit: string)}
  <div class="relative size-28 shrink-0">
    <svg viewBox="0 0 120 120" class="size-full -rotate-90">
      <circle
        cx="60"
        cy="60"
        r={R}
        fill="none"
        stroke="currentColor"
        stroke-width="9"
        class="text-muted-foreground/15"
      />
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
    <div class="absolute inset-0 flex flex-col items-center justify-center">
      <span class="text-2xl font-bold tabular-nums tracking-tight">{center}</span>
      {#if unit}<span class="text-[11px] text-muted-foreground">{unit}</span>{/if}
    </div>
  </div>
{/snippet}

{#snippet statPill(text: string, toneClass: string)}
  <span
    class={cn(
      'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium',
      toneClass
    )}
  >
    <span class="size-1.5 rounded-full bg-current"></span>
    {text}
  </span>
{/snippet}

<div class="space-y-3">
  <div class="flex items-center gap-2">
    <Activity class="size-4 text-primary" />
    <h3 class="text-sm font-semibold">Live metrics</h3>
    {#if metrics}
      <span
        class="ml-auto inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground"
      >
        <span class="size-1.5 animate-pulse rounded-full bg-success"></span>
        Streaming
      </span>
    {/if}
  </div>

  {#if metrics}
    <div class="grid gap-4 sm:grid-cols-2">
      <!-- CPU -->
      <Card class="flex items-center gap-5 p-6">
        {@render gauge(
          metrics.cpu_percent,
          cpuTone.ring,
          `${metrics.cpu_percent.toFixed(0)}%`,
          'used'
        )}
        <div class="min-w-0 space-y-2">
          <div class="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
            <Cpu class="size-4" /> CPU
          </div>
          <div class={cn('text-2xl font-bold tracking-tight tabular-nums', cpuTone.text)}>
            {metrics.cpu_percent.toFixed(1)}<span class="text-base font-normal text-muted-foreground">%</span>
          </div>
          {@render statPill(cpuTone.label, cpuTone.text)}
        </div>
      </Card>

      <!-- Memory -->
      <Card class="flex items-center gap-5 p-6">
        {@render gauge(memPercent, memTone.ring, `${memPercent.toFixed(0)}%`, 'used')}
        <div class="min-w-0 space-y-2">
          <div class="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
            <MemoryStick class="size-4" /> Memory
          </div>
          <div class="text-lg font-semibold tabular-nums">
            {formatBytes(metrics.memory_used_bytes)}
            <span class="text-sm font-normal text-muted-foreground">
              / {formatBytes(metrics.memory_limit_bytes)}
            </span>
          </div>
          {@render statPill(memTone.label, memTone.text)}
        </div>
      </Card>
    </div>
  {:else}
    <Card class="flex items-center gap-3 p-6 text-sm text-muted-foreground">
      <span class="size-2 animate-pulse rounded-full bg-muted-foreground/40"></span>
      Waiting for metrics…
    </Card>
  {/if}
</div>
