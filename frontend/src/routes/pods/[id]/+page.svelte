<script lang="ts">
  import { invalidateAll } from '$app/navigation';
  import GpuMetrics from '$lib/components/GpuMetrics.svelte';
  import { api } from '$lib/api/client';
  import type { Pod, VmMetrics } from '$lib/types';

  let { data }: { data: { pod: Pod | null } } = $props();

  let metrics: VmMetrics | null = $state(null);
  let eventSource: EventSource | null = $state(null);

  // Subscribe to live metrics via SSE — cleanup via $effect return
  $effect(() => {
    if (data.pod?.state === 'running') {
      const es = new EventSource(`/api/pods/${data.pod.id}/metrics`);
      es.addEventListener('metrics', (e) => {
        metrics = JSON.parse(e.data);
      });
      eventSource = es;

      return () => {
        es.close();
        eventSource = null;
      };
    }
  });

  async function terminatePod() {
    if (!data.pod) return;
    try {
      await api.delete(`/pods/${data.pod.id}`);
      await invalidateAll();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to terminate VM');
    }
  }

  const stateColors: Record<string, string> = {
    running: 'bg-green-100 text-green-800',
    pending: 'bg-yellow-100 text-yellow-800',
    creating: 'bg-blue-100 text-blue-800',
    stopping: 'bg-orange-100 text-orange-800',
    terminated: 'bg-gray-100 text-gray-800',
    failed: 'bg-red-100 text-red-800'
  };
</script>

{#if data.pod}
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">VM: {data.pod.id.slice(0, 8)}</h1>
        <span class="mt-1 inline-block rounded-full px-2 py-1 text-xs {stateColors[data.pod.state]}">
          {data.pod.state}
        </span>
      </div>
      {#if data.pod.state !== 'terminated' && data.pod.state !== 'failed'}
        <button
          onclick={terminatePod}
          class="rounded-lg bg-red-600 px-4 py-2 text-white hover:bg-red-700"
        >
          Terminate
        </button>
      {/if}
    </div>

    <div class="rounded-lg border bg-white p-6">
      <h2 class="mb-4 text-lg font-semibold">Details</h2>
      <dl class="grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt class="text-gray-500">Plan</dt>
          <dd class="font-medium capitalize">{data.pod.plan}</dd>
        </div>
        <div>
          <dt class="text-gray-500">Image</dt>
          <dd class="font-medium">{data.pod.image}</dd>
        </div>
        <div>
          <dt class="text-gray-500">Resources</dt>
          <dd class="font-medium">{data.pod.cpu ?? '-'} CPU / {data.pod.memory ?? '-'}</dd>
        </div>
        <div>
          <dt class="text-gray-500">Namespace</dt>
          <dd class="font-medium">{data.pod.namespace}</dd>
        </div>
        {#if data.pod.ssh_port}
          <div class="col-span-2">
            <dt class="text-gray-500">SSH Access</dt>
            <dd class="font-mono text-indigo-600">ssh root@20.193.138.159 -p {data.pod.ssh_port}</dd>
          </div>
        {/if}
        <div>
          <dt class="text-gray-500">Created</dt>
          <dd class="font-medium">{new Date(data.pod.created_at).toLocaleString()}</dd>
        </div>
      </dl>
    </div>

    {#if data.pod.state === 'running'}
      <GpuMetrics {metrics} />
    {/if}
  </div>
{:else}
  <div class="text-center py-12">
    <p class="text-gray-500">VM not found</p>
    <a href="/pods" class="mt-4 inline-block text-indigo-600 hover:underline">Back to VMs</a>
  </div>
{/if}
