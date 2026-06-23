<script lang="ts">
  import { Activity } from 'lucide-svelte';
  import { Card, CardContent, Tabs, Skeleton, Button } from '$lib/ui';
  import UsageChart from './UsageChart.svelte';
  import { api, ApiError } from '$lib/api/client';
  import type { UsageSeries } from '$lib/types';
  import { toast } from 'svelte-sonner';

  let { podId }: { podId: string } = $props();

  type Range = '1h' | '6h' | '24h' | '7d';
  let range = $state<Range>('1h');
  let metric = $state<'cpu' | 'memory'>('cpu');
  let series = $state<UsageSeries | null>(null);
  let loading = $state(false);

  async function load() {
    loading = true;
    try {
      series = await api.get<UsageSeries>(`/usage/${podId}?range=${range}`);
    } catch (e) {
      series = { pod_id: podId, range, data: [] };
      const msg = e instanceof ApiError ? e.message : 'Failed to load usage data';
      toast.error('Could not load usage', { description: msg });
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    range; // track
    load();
  });

  // Hero stats for the active metric (current / avg / peak / low).
  const metricVals = $derived(
    (series?.data ?? []).map((p) =>
      metric === 'cpu' ? p.cpu_percent : p.memory_used_bytes / 1024 ** 3
    )
  );
  const stats = $derived.by(() => {
    const v = metricVals;
    if (!v.length) return null;
    return {
      current: v[v.length - 1],
      avg: v.reduce((a, b) => a + b, 0) / v.length,
      peak: Math.max(...v),
      low: Math.min(...v)
    };
  });
  const unit = $derived(metric === 'cpu' ? '%' : ' GB');
  const toneText = $derived(metric === 'cpu' ? 'text-primary' : 'text-info');
  const fmt = (n: number) => (metric === 'cpu' ? n.toFixed(1) : n.toFixed(2));
</script>

<Card>
  <CardContent class="space-y-4 pt-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="flex items-center gap-2 text-sm font-semibold">
          <Activity class="size-4 text-primary" /> Usage history
        </h3>
        <p class="text-xs text-muted-foreground">
          Time-series CPU and memory from TimescaleDB.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Tabs.Root bind:value={metric} class="hidden sm:block">
          <Tabs.List>
            <Tabs.Trigger value="cpu">CPU</Tabs.Trigger>
            <Tabs.Trigger value="memory">Memory</Tabs.Trigger>
          </Tabs.List>
        </Tabs.Root>
        <div class="inline-flex rounded-md border border-border bg-muted/30 p-0.5">
          {#each ['1h', '6h', '24h', '7d'] as r (r)}
            <button
              class="rounded px-2.5 py-1 text-xs font-medium transition-colors {range === r
                ? 'bg-card text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'}"
              onclick={() => (range = r as Range)}
            >
              {r}
            </button>
          {/each}
        </div>
      </div>
    </div>

    {#if stats}
      <div
        class="flex flex-wrap items-end gap-x-10 gap-y-3 rounded-xl border border-border/60 bg-muted/20 px-5 py-4"
      >
        <div>
          <div class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {metric === 'cpu' ? 'CPU now' : 'Memory now'}
          </div>
          <div class={`mt-1 text-3xl font-bold tabular-nums ${toneText}`}>
            {fmt(stats.current)}<span class="text-lg font-medium text-muted-foreground">{unit}</span>
          </div>
        </div>
        <div class="flex items-end gap-x-8">
          {#each [{ l: 'Avg', v: stats.avg }, { l: 'Peak', v: stats.peak }, { l: 'Low', v: stats.low }] as s (s.l)}
            <div>
              <div class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {s.l}
              </div>
              <div class="mt-1 text-base font-semibold tabular-nums">
                {fmt(s.v)}<span class="text-xs font-normal text-muted-foreground">{unit}</span>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if loading && !series}
      <Skeleton class="h-[22rem] w-full" />
    {:else if series && series.data.length > 0}
      <UsageChart points={series.data} {metric} height={320} />
    {:else}
      <div
        class="flex h-[22rem] flex-col items-center justify-center rounded-xl border border-dashed bg-muted/20 text-sm text-muted-foreground"
      >
        <div class="flex size-12 items-center justify-center rounded-full bg-muted/60 text-muted-foreground">
          <Activity class="size-6 opacity-70" />
        </div>
        <p class="mt-3 font-medium text-foreground">No usage data yet for this range</p>
        <p class="mt-0.5 text-xs">
          Metrics start appearing a few minutes after the VM is running.
        </p>
      </div>
    {/if}
  </CardContent>
</Card>
