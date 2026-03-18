<script lang="ts">
  import type { Pod } from '$lib/types';

  let { pod }: { pod: Pod } = $props();

  const stateColors: Record<string, string> = {
    running: 'bg-green-100 text-green-800',
    pending: 'bg-yellow-100 text-yellow-800',
    creating: 'bg-blue-100 text-blue-800',
    stopping: 'bg-orange-100 text-orange-800',
    terminated: 'bg-gray-100 text-gray-800',
    failed: 'bg-red-100 text-red-800'
  };
</script>

<div class="rounded-lg border bg-white p-4 shadow-sm hover:shadow-md transition-shadow">
  <div class="flex items-center justify-between">
    <h3 class="font-mono text-sm font-semibold">{pod.id.slice(0, 8)}</h3>
    <span class="rounded-full px-2 py-1 text-xs {stateColors[pod.state]}">
      {pod.state}
    </span>
  </div>
  <div class="mt-3 space-y-1 text-sm text-gray-600">
    <p>Plan: <span class="font-medium text-gray-900 capitalize">{pod.plan}</span></p>
    <p>Image: <span class="font-medium text-gray-900">{pod.image}</span></p>
    {#if pod.cpu && pod.memory}
      <p>Resources: {pod.cpu} CPU / {pod.memory}</p>
    {/if}
    {#if pod.ssh_port && pod.state === 'running'}
      <p class="text-indigo-600">SSH port: {pod.ssh_port}</p>
    {/if}
  </div>
</div>
