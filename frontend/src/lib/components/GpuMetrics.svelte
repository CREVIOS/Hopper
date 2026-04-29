<script lang="ts">
  import { Cpu, MemoryStick, Activity } from 'lucide-svelte';
  import type { VmMetrics } from '$lib/types';
  import { Card, Progress } from '$lib/ui';
  import { formatBytes } from '$lib/utils';

  let { metrics }: { metrics: VmMetrics | null } = $props();

  const memPercent = $derived(
    metrics && metrics.memory_limit_bytes > 0
      ? (metrics.memory_used_bytes / metrics.memory_limit_bytes) * 100
      : 0
  );

  function indicatorClass(pct: number): string {
    if (pct > 80) return 'bg-destructive';
    if (pct > 60) return 'bg-warning';
    return 'bg-primary';
  }
</script>

<Card class="p-5">
  <div class="mb-4 flex items-center gap-2">
    <Activity class="size-4 text-primary" />
    <h3 class="text-sm font-semibold">Live metrics</h3>
    {#if metrics}
      <span
        class="ml-auto inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground"
      >
        <span class="size-1.5 rounded-full bg-success animate-pulse"></span>
        Streaming
      </span>
    {/if}
  </div>

  {#if metrics}
    <div class="grid gap-5 sm:grid-cols-2">
      <div>
        <div class="mb-2 flex items-baseline justify-between">
          <span class="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Cpu class="size-3.5" /> CPU
          </span>
          <span class="text-2xl font-bold tracking-tight">
            {metrics.cpu_percent.toFixed(1)}<span class="text-sm font-normal text-muted-foreground">%</span>
          </span>
        </div>
        <Progress
          value={Math.min(metrics.cpu_percent, 100)}
          indicatorClass={indicatorClass(metrics.cpu_percent)}
        />
      </div>

      <div>
        <div class="mb-2 flex items-baseline justify-between">
          <span class="flex items-center gap-1.5 text-sm text-muted-foreground">
            <MemoryStick class="size-3.5" /> Memory
          </span>
          <span class="text-base font-semibold tabular-nums">
            {formatBytes(metrics.memory_used_bytes)}
            <span class="text-sm font-normal text-muted-foreground">
              / {formatBytes(metrics.memory_limit_bytes)}
            </span>
          </span>
        </div>
        <Progress value={memPercent} indicatorClass={indicatorClass(memPercent)} />
      </div>
    </div>
  {:else}
    <div class="flex items-center gap-2 py-4 text-sm text-muted-foreground">
      <span class="size-2 rounded-full bg-muted-foreground/40 animate-pulse"></span>
      Waiting for metrics…
    </div>
  {/if}
</Card>
