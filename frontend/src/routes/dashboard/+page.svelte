<script lang="ts">
  import PodCard from '$lib/components/PodCard.svelte';
  import CreditBadge from '$lib/components/CreditBadge.svelte';
  import type { Pod } from '$lib/types';

  let { data }: { data: { balance: number; pods: Pod[] } } = $props();
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <h1 class="text-2xl font-bold">Dashboard</h1>
    <CreditBadge balance={data.balance} />
  </div>

  <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
    {#each data.pods as pod (pod.id)}
      <a href="/pods/{pod.id}" class="block">
        <PodCard {pod} />
      </a>
    {:else}
      <p class="text-gray-500">No active pods. Launch one to get started.</p>
    {/each}
  </div>

  <a
    href="/pods"
    class="inline-block rounded-lg bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700"
  >
    Launch Pod
  </a>
</div>
