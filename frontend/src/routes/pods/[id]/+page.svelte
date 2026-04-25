<script lang="ts">
  import { invalidateAll } from '$app/navigation';
  import GpuMetrics from '$lib/components/GpuMetrics.svelte';
  import Terminal from '$lib/components/Terminal.svelte';
  import { api } from '$lib/api/client';
  import type { Pod, VmMetrics } from '$lib/types';

  let { data }: { data: { pod: Pod | null } } = $props();

  let metrics: VmMetrics | null = $state(null);
  let eventSource: EventSource | null = $state(null);

  // Tab management
  let activeTab = $state('terminal'); // 'terminal', 'vscode', 'metrics', 'details'
  
  // Terminal sessions management
  let terminalSessions = $state([{ id: 'term-1' }]);
  let activeTerminalId = $state('term-1');

  function addTerminal() {
    const id = `term-${Date.now()}`;
    terminalSessions = [...terminalSessions, { id }];
    activeTerminalId = id;
  }

  function removeTerminal(id: string) {
    terminalSessions = terminalSessions.filter(t => t.id !== id);
    if (activeTerminalId === id && terminalSessions.length > 0) {
      activeTerminalId = terminalSessions[terminalSessions.length - 1].id;
    }
    if (terminalSessions.length === 0) {
      addTerminal();
    }
  }

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
  <div class="flex flex-col h-[calc(100vh-6rem)]">
    <div class="flex items-center justify-between mb-4">
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

    <!-- Tabs Header -->
    <div class="border-b border-gray-200 mb-4">
      <nav class="-mb-px flex space-x-8">
        {#each ['terminal', 'vscode', 'metrics', 'details'] as tab}
          <button
            class="capitalize py-2 border-b-2 font-medium text-sm {activeTab === tab ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}"
            onclick={() => activeTab = tab}
          >
            {tab === 'vscode' ? 'VS Code' : tab}
          </button>
        {/each}
      </nav>
    </div>

    <!-- Tab Content -->
    <div class="flex-grow min-h-0 relative">
      {#if activeTab === 'terminal'}
        <div class="h-full flex flex-col border border-gray-200 rounded-lg overflow-hidden bg-gray-50">
          <div class="flex bg-gray-200 overflow-x-auto border-b border-gray-300 items-center">
            {#each terminalSessions as session, idx}
              <button
                class="flex items-center px-4 py-2 text-sm border-r border-gray-300 min-w-32 {activeTerminalId === session.id ? 'bg-white font-medium text-indigo-600' : 'hover:bg-gray-300 text-gray-600'}"
                onclick={() => activeTerminalId = session.id}
              >
                <svg class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                Terminal {idx + 1}
                <button
                  class="ml-auto w-5 h-5 flex items-center justify-center rounded hover:bg-gray-400 hover:text-gray-900"
                  onclick={(e) => { e.stopPropagation(); removeTerminal(session.id); }}
                  title="Close Terminal"
                >
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
              </button>
            {/each}
            <button
               class="px-3 py-2 text-gray-500 hover:bg-gray-300 hover:text-gray-800 focus:outline-none"
               onclick={addTerminal}
               title="New Terminal"
            >
               <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path></svg>
            </button>
          </div>
          
          <div class="flex-grow min-h-0 bg-black relative">
            {#if data.pod.state !== 'running'}
              <div class="absolute inset-0 flex items-center justify-center bg-black/80 z-20 text-white flex-col space-y-4">
                 <svg class="w-12 h-12 text-gray-400 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01"></path></svg>
                 <p>VM is {data.pod.state}. SSH access is only available when running.</p>
              </div>
            {/if}
            {#each terminalSessions as session}
              <div class="absolute inset-0 {activeTerminalId === session.id ? 'opacity-100 z-10' : 'opacity-0 z-0 pointer-events-none'}">
                <Terminal podId={data.pod.id} sessionId={session.id} />
              </div>
            {/each}
          </div>
        </div>
      {:else if activeTab === 'details'}
        <div class="rounded-lg border bg-white p-6 overflow-y-auto h-full">
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
      {:else if activeTab === 'metrics'}
        <div class="h-full overflow-y-auto">
          {#if data.pod.state === 'running'}
            <GpuMetrics {metrics} />
          {:else}
            <div class="text-center py-12 border bg-white rounded-lg h-full flex flex-col items-center justify-center">
              <p class="text-gray-500">Metrics are only available for running VMs</p>
            </div>
          {/if}
        </div>
      {:else}
        <div class="flex items-center justify-center h-full bg-gray-50 border rounded-lg border-dashed border-gray-300">
           <p class="text-gray-500">Coming soon</p>
        </div>
      {/if}
    </div>
  </div>
{:else}
  <div class="text-center py-12">
    <p class="text-gray-500">VM not found</p>
    <a href="/pods" class="mt-4 inline-block text-indigo-600 hover:underline">Back to VMs</a>
  </div>
{/if}
