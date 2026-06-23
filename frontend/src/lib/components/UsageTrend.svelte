<script lang="ts">
  import { Activity } from 'lucide-svelte';
  import { Card, CardContent, Tabs, Skeleton } from '$lib/ui';
  import UsageChart from './UsageChart.svelte';
  import { api, ApiError } from '$lib/api/client';
  import type { UsageSeries } from '$lib/types';
  import { toast } from 'svelte-sonner';

  type Range = '1h' | '6h' | '24h' | '7d';
  let range = $state<Range>('24h');
  let metric = $state<'cpu' | 'memory'>('cpu');
  let series = $state<UsageSeries | null>(null);
  let loading = $state(false);

  async function load() {
    loading = true;
    try {
      series = await api.get<UsageSeries>(`/usage/summary/me/series?range=${range}`);
    } catch (e) {
      series = { pod_id: 'me', range, data: [] };
      const msg = e instanceof ApiError ? e.message : 'Failed to load usage history';
      toast.error('Could not load usage trend', { description: msg });
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    range;
    load();
  });
</script>

<Card>
  <CardContent class="space-y-4 pt-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="flex items-center gap-2 text-sm font-semibold">
          <Activity class="size-4 text-primary" /> Your usage over time
        </h3>
        <p class="text-xs text-muted-foreground">
          Aggregated across all your VMs. A trend, not a snapshot — useful for spotting
          peak times or unusually idle periods.
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

    {#if loading && !series}
      <Skeleton class="h-44 w-full" />
    {:else if series && series.data.length > 0}
      <UsageChart points={series.data} {metric} height={200} />
    {:else}
      <div
        class="flex h-44 flex-col items-center justify-center rounded-lg border border-dashed bg-muted/20 text-sm text-muted-foreground"
      >
        <div
          class="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary"
        >
          <Activity class="size-5" />
        </div>
        <p class="mt-2 font-medium text-foreground">No usage data yet</p>
        <p class="mt-0.5 text-xs">
          Metrics begin recording a few minutes after your first VM starts.
        </p>
      </div>
    {/if}
  </CardContent>
</Card>
