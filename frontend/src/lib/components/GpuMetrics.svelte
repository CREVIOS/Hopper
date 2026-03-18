<script lang="ts">
  import type { VmMetrics } from '$lib/types';

  let { metrics }: { metrics: VmMetrics | null } = $props();

  function formatBytes(bytes: number): string {
    if (bytes === 0) return '0 B';
    const gb = bytes / (1024 * 1024 * 1024);
    if (gb >= 1) return `${gb.toFixed(1)} GB`;
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(0)} MB`;
  }
</script>

<div class="rounded-lg border bg-white p-4">
  <h3 class="mb-2 font-semibold">VM Metrics</h3>
  {#if metrics}
    <div class="grid grid-cols-2 gap-4 text-sm">
      <div>
        <p class="text-gray-500">CPU Usage</p>
        <p class="text-lg font-semibold">{metrics.cpu_percent.toFixed(1)}%</p>
      </div>
      <div>
        <p class="text-gray-500">Memory</p>
        <p class="text-lg font-semibold">
          {formatBytes(metrics.memory_used_bytes)} / {formatBytes(metrics.memory_limit_bytes)}
        </p>
      </div>
    </div>
  {:else}
    <p class="text-sm text-gray-500">No metrics available</p>
  {/if}
</div>
