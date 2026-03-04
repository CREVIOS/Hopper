<script lang="ts">
  import { page } from '$app/state';
  import GpuMetrics from '$lib/components/GpuMetrics.svelte';
  import Terminal from '$lib/components/Terminal.svelte';
  import { activePodMetrics } from '$lib/stores/pods';

  const podId = $derived(page.params.id);
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <h1 class="text-2xl font-bold">Pod: {podId}</h1>
    <button class="rounded-lg bg-red-600 px-4 py-2 text-white hover:bg-red-700">
      Terminate
    </button>
  </div>

  <GpuMetrics metrics={$activePodMetrics} />
  <Terminal sessionId={podId} />
</div>
