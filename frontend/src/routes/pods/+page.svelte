<script lang="ts">
  import PodCard from '$lib/components/PodCard.svelte';
  import { pods } from '$lib/stores/pods';
  import { GPU_TIER_RATES, type GpuTier } from '$lib/types';

  let selectedTier: GpuTier = $state('standard');

  async function createPod() {
    // TODO: POST /api/pods with selectedTier
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
        class="rounded-lg bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700"
      >
        Launch Pod
      </button>
    </div>
  </div>

  <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
    {#each $pods as pod (pod.id)}
      <a href="/pods/{pod.id}" class="block">
        <PodCard {pod} />
      </a>
    {:else}
      <p class="text-gray-500">No pods yet.</p>
    {/each}
  </div>
</div>
