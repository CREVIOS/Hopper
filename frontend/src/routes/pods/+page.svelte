<script lang="ts">
  import PodCard from '$lib/components/PodCard.svelte';
  import { GPU_TIER_RATES, type GpuTier, type Pod } from '$lib/types';
  import { api } from '$lib/api/client';
  import { invalidateAll } from '$app/navigation';

  let { data }: { data: { pods: Pod[] } } = $props();

  let selectedTier: GpuTier = $state('standard');
  let creating = $state(false);

  async function createPod() {
    creating = true;
    try {
      await api.post('/pods', { gpu_tier: selectedTier });
      await invalidateAll();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to create pod');
    } finally {
      creating = false;
    }
  }

  async function terminatePod(podId: string) {
    try {
      await api.delete(`/pods/${podId}`);
      await invalidateAll();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to terminate pod');
    }
  }
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <h1 class="text-2xl font-bold">GPU Pods</h1>
    <div class="flex items-center gap-3">
      <select bind:value={selectedTier} class="rounded border px-3 py-2">
        {#each Object.entries(GPU_TIER_RATES) as [tier, rate]}
          <option value={tier}>{tier} ({rate} cr/hr)</option>
        {/each}
      </select>
      <button
        onclick={createPod}
        disabled={creating}
        class="rounded-lg bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {creating ? 'Launching...' : 'Launch Pod'}
      </button>
    </div>
  </div>

  <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
    {#each data.pods as pod (pod.id)}
      <div class="relative">
        <a href="/pods/{pod.id}" class="block">
          <PodCard {pod} />
        </a>
        {#if pod.state !== 'terminated' && pod.state !== 'stopping'}
          <button
            onclick={() => terminatePod(pod.id)}
            class="absolute right-2 top-2 rounded bg-red-100 px-2 py-1 text-xs text-red-700 hover:bg-red-200"
          >
            Terminate
          </button>
        {/if}
      </div>
    {:else}
      <p class="text-gray-500">No pods yet.</p>
    {/each}
  </div>
</div>
