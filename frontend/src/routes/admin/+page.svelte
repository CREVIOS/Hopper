<script lang="ts">
  let { data }: { data: {
    stats: { total_users: number; active_vms: number; total_vms_created: number };
    nodes: Array<{ name: string; cpu_capacity: string; memory_capacity: string; cpu_allocatable: string; memory_allocatable: string; pod_count: number; ready: boolean }>;
    users: Array<{ id: string; email: string; name: string; role: string; created_at: string }>;
  }} = $props();

  function formatMemory(ki: string): string {
    const gb = parseInt(ki.replace('Ki', '')) / (1024 * 1024);
    return `${gb.toFixed(1)} GB`;
  }
</script>

<div class="space-y-6">
  <h1 class="text-2xl font-bold">Admin Dashboard</h1>

  <!-- Stats -->
  <div class="grid gap-6 md:grid-cols-3">
    <div class="rounded-lg border bg-white p-6">
      <h2 class="text-lg font-semibold">Users</h2>
      <p class="mt-2 text-3xl font-bold">{data.stats.total_users}</p>
      <p class="text-sm text-gray-500">Total registered</p>
    </div>
    <div class="rounded-lg border bg-white p-6">
      <h2 class="text-lg font-semibold">Active VMs</h2>
      <p class="mt-2 text-3xl font-bold">{data.stats.active_vms}</p>
      <p class="text-sm text-gray-500">Currently running</p>
    </div>
    <div class="rounded-lg border bg-white p-6">
      <h2 class="text-lg font-semibold">Total VMs</h2>
      <p class="mt-2 text-3xl font-bold">{data.stats.total_vms_created}</p>
      <p class="text-sm text-gray-500">All time</p>
    </div>
  </div>

  <!-- Nodes -->
  <div>
    <h2 class="mb-3 text-xl font-semibold">Compute Nodes</h2>
    {#if data.nodes.length > 0}
      <div class="rounded-lg border bg-white overflow-hidden">
        <table class="w-full">
          <thead class="border-b bg-gray-50">
            <tr>
              <th class="px-4 py-2 text-left text-sm">Node</th>
              <th class="px-4 py-2 text-left text-sm">Status</th>
              <th class="px-4 py-2 text-left text-sm">CPU</th>
              <th class="px-4 py-2 text-left text-sm">Memory</th>
              <th class="px-4 py-2 text-left text-sm">VMs</th>
            </tr>
          </thead>
          <tbody>
            {#each data.nodes as node}
              <tr class="border-b">
                <td class="px-4 py-2 text-sm font-mono">{node.name}</td>
                <td class="px-4 py-2 text-sm">
                  <span class="rounded-full px-2 py-1 text-xs {node.ready ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}">
                    {node.ready ? 'Ready' : 'Not Ready'}
                  </span>
                </td>
                <td class="px-4 py-2 text-sm">{node.cpu_allocatable} / {node.cpu_capacity}</td>
                <td class="px-4 py-2 text-sm">{formatMemory(node.memory_allocatable)} / {formatMemory(node.memory_capacity)}</td>
                <td class="px-4 py-2 text-sm">{node.pod_count}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <p class="text-gray-500">No nodes available</p>
    {/if}
  </div>

  <!-- Users -->
  <div>
    <h2 class="mb-3 text-xl font-semibold">Users</h2>
    {#if data.users.length > 0}
      <div class="rounded-lg border bg-white overflow-hidden">
        <table class="w-full">
          <thead class="border-b bg-gray-50">
            <tr>
              <th class="px-4 py-2 text-left text-sm">Name</th>
              <th class="px-4 py-2 text-left text-sm">Email</th>
              <th class="px-4 py-2 text-left text-sm">Role</th>
              <th class="px-4 py-2 text-left text-sm">Joined</th>
            </tr>
          </thead>
          <tbody>
            {#each data.users as u}
              <tr class="border-b">
                <td class="px-4 py-2 text-sm">{u.name}</td>
                <td class="px-4 py-2 text-sm">{u.email}</td>
                <td class="px-4 py-2 text-sm capitalize">{u.role}</td>
                <td class="px-4 py-2 text-sm">{u.created_at ? new Date(u.created_at).toLocaleDateString() : '-'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <p class="text-gray-500">No users registered yet</p>
    {/if}
  </div>
</div>
