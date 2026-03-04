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

<div class="rounded-lg border p-4 shadow-sm">
  <div class="flex items-center justify-between">
    <h3 class="font-semibold">{pod.id}</h3>
    <span class="rounded-full px-2 py-1 text-xs {stateColors[pod.state]}">
      {pod.state}
    </span>
  </div>
  <p class="mt-2 text-sm text-gray-600">GPU: {pod.gpu_tier}</p>
  <p class="text-sm text-gray-600">Image: {pod.image}</p>
</div>
