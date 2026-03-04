<script lang="ts">
  import type { GpuMetrics } from '$lib/types';

  let { metrics }: { metrics: GpuMetrics | null } = $props();
</script>

<div class="rounded-lg border p-4">
  <h3 class="mb-2 font-semibold">GPU Metrics</h3>
  {#if metrics}
    <div class="grid grid-cols-2 gap-2 text-sm">
      <div>Utilization: {metrics.gpu_utilization.toFixed(1)}%</div>
      <div>Temperature: {metrics.temperature.toFixed(0)}C</div>
      <div>VRAM: {(metrics.memory_used / 1e9).toFixed(1)} / {(metrics.memory_total / 1e9).toFixed(1)} GB</div>
      <div>Power: {metrics.power_usage.toFixed(0)}W</div>
    </div>
  {:else}
    <p class="text-sm text-gray-500">No metrics available</p>
  {/if}
</div>
