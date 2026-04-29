<script lang="ts">
  import {
    Users,
    Server,
    Database,
    Activity,
    Coins,
    Plus,
    Search,
    Loader2,
    ShieldAlert,
    HardDrive,
    Cpu,
    MemoryStick
  } from 'lucide-svelte';
  import { invalidateAll } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import {
    Button,
    Card,
    CardContent,
    Input,
    Label,
    Badge,
    Tabs,
    Tooltip,
    Dialog,
    Progress,
    Separator
  } from '$lib/ui';
  import StatCard from '$lib/components/StatCard.svelte';
  import Avatar from '$lib/ui/avatar.svelte';
  import { api, ApiError } from '$lib/api/client';
  import { relTime, shortId } from '$lib/utils';

  type ActiveVm = {
    id: string;
    state: string;
    plan: string;
    image: string;
    cpu: string | null;
    memory: string | null;
    user_email: string | null;
    user_name: string | null;
    started_at: string | null;
  };
  type AuditLog = {
    id: string;
    user_id: string | null;
    action: string;
    resource_type: string | null;
    resource_id: string | null;
    ip_address: string | null;
    status_code: number | null;
    created_at: string | null;
  };
  type Node = {
    name: string;
    cpu_capacity: string;
    memory_capacity: string;
    cpu_allocatable: string;
    memory_allocatable: string;
    pod_count: number;
    ready: boolean;
  };
  type AdminUser = {
    id: string;
    email: string;
    name: string;
    role: string;
    created_at: string | null;
  };

  let {
    data
  }: {
    data: {
      currentUserId: string;
      currentUserRole: string;
      stats: {
        total_users: number;
        active_vms: number;
        total_vms_created: number;
      };
      nodes: Node[];
      users: AdminUser[];
      activeVms: ActiveVm[];
      auditLogs: AuditLog[];
    };
  } = $props();

  let tab = $state('overview');
  let userQuery = $state('');
  let vmQuery = $state('');

  // Role mutation state — kept local so the dropdown updates instantly
  // before invalidateAll() refreshes the list from the server.
  let users = $state<AdminUser[]>(data.users);
  let pendingRoleChange = $state<string | null>(null);

  $effect(() => {
    users = data.users;
  });

  async function changeRole(u: AdminUser, newRole: string) {
    if (newRole === u.role) return;
    if (data.currentUserRole !== 'admin') return;
    if (u.id === data.currentUserId && newRole !== 'admin') {
      toast.error('You cannot demote yourself');
      return;
    }
    const previous = u.role;
    pendingRoleChange = u.id;
    u.role = newRole;
    const tid = toast.loading(`Changing role for ${u.email}…`);
    try {
      await api.patch(`/admin/users/${u.id}/role`, { role: newRole });
      toast.success(`${u.email} → ${newRole}`, { id: tid });
      await invalidateAll();
    } catch (e) {
      u.role = previous;
      const msg = e instanceof ApiError ? e.message : 'Role change failed';
      toast.error('Could not change role', { id: tid, description: msg });
    } finally {
      pendingRoleChange = null;
    }
  }

  // Credit allocation dialog state
  let allocOpen = $state(false);
  let allocUser = $state<AdminUser | null>(null);
  let allocAmount = $state(10);
  let allocDescription = $state('Manual allocation');
  let allocating = $state(false);

  function openAlloc(u: AdminUser) {
    allocUser = u;
    allocAmount = 10;
    allocDescription = `Allocation for ${u.name || u.email}`;
    allocOpen = true;
  }

  async function allocate() {
    if (!allocUser || allocating) return;
    if (!Number.isFinite(allocAmount) || allocAmount <= 0) {
      toast.error('Amount must be a positive number');
      return;
    }
    allocating = true;
    const id = toast.loading(
      `Allocating ${allocAmount} credit${allocAmount === 1 ? '' : 's'}…`
    );
    try {
      await api.post('/credits/allocate', {
        user_id: allocUser.id,
        amount: allocAmount,
        description: allocDescription || 'allocation'
      });
      toast.success(`Allocated ${allocAmount.toFixed(2)} credits`, {
        id,
        description: `${allocUser.name || allocUser.email}`
      });
      allocOpen = false;
      await invalidateAll();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Allocation failed';
      toast.error('Could not allocate credits', { id, description: msg });
    } finally {
      allocating = false;
    }
  }

  function memoryToGb(s: string | null | undefined): number | null {
    if (!s) return null;
    const m = s.match(/^(\d+)(Ki|Mi|Gi)?$/);
    if (!m) return null;
    const v = parseInt(m[1]);
    if (m[2] === 'Ki') return v / (1024 * 1024);
    if (m[2] === 'Mi') return v / 1024;
    if (m[2] === 'Gi') return v;
    return v / (1024 * 1024 * 1024);
  }

  function fmtMem(s: string | null | undefined): string {
    const gb = memoryToGb(s);
    if (gb === null) return s ?? '-';
    return `${gb.toFixed(1)} GB`;
  }

  const filteredUsers = $derived(
    userQuery
      ? users.filter(
          (u) =>
            u.email.toLowerCase().includes(userQuery.toLowerCase()) ||
            u.name.toLowerCase().includes(userQuery.toLowerCase()) ||
            u.role.toLowerCase().includes(userQuery.toLowerCase())
        )
      : users
  );

  const filteredVms = $derived(
    vmQuery
      ? data.activeVms.filter(
          (v) =>
            v.id.toLowerCase().includes(vmQuery.toLowerCase()) ||
            (v.user_email ?? '').toLowerCase().includes(vmQuery.toLowerCase()) ||
            (v.user_name ?? '').toLowerCase().includes(vmQuery.toLowerCase())
        )
      : data.activeVms
  );

  const stateBadge: Record<
    string,
    'success' | 'warning' | 'info' | 'destructive' | 'muted'
  > = {
    running: 'success',
    pending: 'warning',
    creating: 'info',
    stopping: 'warning',
    terminated: 'muted',
    failed: 'destructive'
  };

  const roleBadge: Record<string, 'default' | 'info' | 'muted'> = {
    admin: 'default',
    professor: 'info',
    student: 'muted'
  };

  function statusTone(code: number | null): string {
    if (!code) return 'text-muted-foreground';
    if (code >= 500) return 'text-destructive';
    if (code >= 400) return 'text-warning';
    return 'text-success';
  }
</script>

<div class="space-y-8">
  <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
    <div>
      <div
        class="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs font-medium text-muted-foreground"
      >
        <ShieldAlert class="size-3 text-primary" /> Admin console
      </div>
      <h1 class="mt-2 text-3xl font-bold tracking-tight">Admin</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Platform overview, user management, and audit trail.
      </p>
    </div>
  </div>

  <!-- Stats -->
  <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
    <StatCard
      label="Total users"
      value={data.stats.total_users}
      icon={Users}
      tone="primary"
    />
    <StatCard
      label="Active VMs"
      value={data.stats.active_vms}
      icon={Server}
      tone="success"
    />
    <StatCard
      label="VMs all-time"
      value={data.stats.total_vms_created}
      icon={Database}
      tone="info"
    />
    <StatCard
      label="Compute nodes"
      value={data.nodes.length}
      sub={`${data.nodes.filter((n) => n.ready).length} ready`}
      icon={Activity}
      tone={data.nodes.every((n) => n.ready) ? 'success' : 'warning'}
    />
  </div>

  <!-- Tabs -->
  <Tabs.Root bind:value={tab}>
    <Tabs.List class="w-full justify-start sm:w-auto">
      <Tabs.Trigger value="overview">Overview</Tabs.Trigger>
      <Tabs.Trigger value="users">Users</Tabs.Trigger>
      <Tabs.Trigger value="vms">Active VMs</Tabs.Trigger>
      <Tabs.Trigger value="nodes">Nodes</Tabs.Trigger>
      <Tabs.Trigger value="audit">Audit log</Tabs.Trigger>
    </Tabs.List>

    <!-- Overview -->
    <Tabs.Content value="overview">
      <div class="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent class="space-y-4 pt-6">
            <h3 class="text-sm font-semibold">Recent activity</h3>
            <Separator />
            {#if data.auditLogs.length === 0}
              <p class="text-sm text-muted-foreground">No events yet.</p>
            {:else}
              <ul class="divide-y divide-border">
                {#each data.auditLogs.slice(0, 6) as log (log.id)}
                  <li class="flex items-center gap-3 py-2 text-sm">
                    <span
                      class={`size-2 rounded-full ${
                        log.status_code && log.status_code >= 400
                          ? 'bg-destructive'
                          : 'bg-success'
                      }`}
                    ></span>
                    <span class="font-medium">{log.action}</span>
                    <span class="ml-auto text-xs text-muted-foreground">
                      {relTime(log.created_at)}
                    </span>
                  </li>
                {/each}
              </ul>
            {/if}
          </CardContent>
        </Card>

        <Card>
          <CardContent class="space-y-4 pt-6">
            <h3 class="text-sm font-semibold">Cluster pressure</h3>
            <Separator />
            {#if data.nodes.length === 0}
              <p class="text-sm text-muted-foreground">No nodes reporting.</p>
            {:else}
              {@const totalCpu = data.nodes.reduce((a, n) => a + (parseFloat(n.cpu_capacity) || 0), 0)}
              {@const allocCpu = data.nodes.reduce((a, n) => a + (parseFloat(n.cpu_allocatable) || 0), 0)}
              {@const totalMem = data.nodes.reduce((a, n) => a + (memoryToGb(n.memory_capacity) || 0), 0)}
              {@const allocMem = data.nodes.reduce((a, n) => a + (memoryToGb(n.memory_allocatable) || 0), 0)}
              {@const cpuUsedPct = totalCpu ? ((totalCpu - allocCpu) / totalCpu) * 100 : 0}
              {@const memUsedPct = totalMem ? ((totalMem - allocMem) / totalMem) * 100 : 0}
              <div>
                <div class="mb-1.5 flex items-baseline justify-between text-sm">
                  <span class="flex items-center gap-1.5 text-muted-foreground">
                    <Cpu class="size-3.5" /> CPU reserved
                  </span>
                  <span class="font-semibold">{cpuUsedPct.toFixed(0)}%</span>
                </div>
                <Progress value={cpuUsedPct} />
                <p class="mt-1 text-xs text-muted-foreground">
                  {(totalCpu - allocCpu).toFixed(1)} of {totalCpu.toFixed(1)} cores reserved
                </p>
              </div>
              <div>
                <div class="mb-1.5 flex items-baseline justify-between text-sm">
                  <span class="flex items-center gap-1.5 text-muted-foreground">
                    <MemoryStick class="size-3.5" /> Memory reserved
                  </span>
                  <span class="font-semibold">{memUsedPct.toFixed(0)}%</span>
                </div>
                <Progress value={memUsedPct} />
                <p class="mt-1 text-xs text-muted-foreground">
                  {(totalMem - allocMem).toFixed(1)} of {totalMem.toFixed(1)} GB reserved
                </p>
              </div>
            {/if}
          </CardContent>
        </Card>
      </div>
    </Tabs.Content>

    <!-- Users -->
    <Tabs.Content value="users">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-base font-semibold">Users ({data.users.length})</h2>
        <div class="relative">
          <Search
            class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            placeholder="Search users…"
            bind:value={userQuery}
            class="h-9 w-64 pl-8"
          />
        </div>
      </div>

      <Card class="overflow-hidden">
        <table class="w-full">
          <thead class="border-b border-border bg-muted/30">
            <tr class="text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <th class="px-4 py-3">User</th>
              <th class="px-4 py-3">Email</th>
              <th class="px-4 py-3">Role</th>
              <th class="px-4 py-3">Joined</th>
              <th class="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            {#each filteredUsers as u (u.id)}
              <tr class="text-sm transition-colors hover:bg-muted/30">
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2.5">
                    <Avatar name={u.name || u.email} class="size-7" />
                    <div class="font-medium">{u.name || '—'}</div>
                  </div>
                </td>
                <td class="px-4 py-3 text-muted-foreground">{u.email}</td>
                <td class="px-4 py-3">
                  {#if data.currentUserRole === 'admin' && u.id !== data.currentUserId}
                    <select
                      class="rounded-md border border-border bg-background px-2 py-1 text-xs font-medium capitalize disabled:opacity-50"
                      value={u.role}
                      disabled={pendingRoleChange === u.id}
                      onchange={(e) =>
                        changeRole(u, (e.currentTarget as HTMLSelectElement).value)}
                      aria-label={`Change role for ${u.email}`}
                    >
                      <option value="student">Student</option>
                      <option value="professor">Professor</option>
                      <option value="admin">Admin</option>
                    </select>
                  {:else}
                    <Badge variant={roleBadge[u.role] ?? 'muted'} class="capitalize">
                      {u.role}
                    </Badge>
                  {/if}
                </td>
                <td class="px-4 py-3 text-muted-foreground">
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                </td>
                <td class="px-4 py-3 text-right">
                  <Tooltip content="Allocate credits to this user">
                    <Button variant="outline" size="sm" onclick={() => openAlloc(u)}>
                      <Coins class="size-3.5" /> Allocate
                    </Button>
                  </Tooltip>
                </td>
              </tr>
            {/each}
            {#if filteredUsers.length === 0}
              <tr>
                <td colspan="5" class="px-4 py-8 text-center text-sm text-muted-foreground">
                  No users match your search.
                </td>
              </tr>
            {/if}
          </tbody>
        </table>
      </Card>
    </Tabs.Content>

    <!-- Active VMs -->
    <Tabs.Content value="vms">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-base font-semibold">Active VMs ({data.activeVms.length})</h2>
        <div class="relative">
          <Search
            class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            placeholder="Search VMs or owners…"
            bind:value={vmQuery}
            class="h-9 w-64 pl-8"
          />
        </div>
      </div>

      <Card class="overflow-hidden">
        <table class="w-full">
          <thead class="border-b border-border bg-muted/30">
            <tr class="text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <th class="px-4 py-3">VM</th>
              <th class="px-4 py-3">Owner</th>
              <th class="px-4 py-3">Plan</th>
              <th class="px-4 py-3">Resources</th>
              <th class="px-4 py-3">State</th>
              <th class="px-4 py-3 text-right">Started</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            {#each filteredVms as vm (vm.id)}
              <tr class="text-sm transition-colors hover:bg-muted/30">
                <td class="px-4 py-3 font-mono text-xs">{shortId(vm.id, 10)}</td>
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <Avatar name={vm.user_name || vm.user_email} class="size-6" />
                    <div>
                      <div class="font-medium">{vm.user_name ?? '—'}</div>
                      <div class="text-xs text-muted-foreground">
                        {vm.user_email ?? ''}
                      </div>
                    </div>
                  </div>
                </td>
                <td class="px-4 py-3 capitalize">{vm.plan}</td>
                <td class="px-4 py-3 text-xs text-muted-foreground">
                  {vm.cpu ?? '—'} CPU · {vm.memory ?? '—'}
                </td>
                <td class="px-4 py-3">
                  <Badge variant={stateBadge[vm.state] ?? 'muted'} class="capitalize">
                    {vm.state}
                  </Badge>
                </td>
                <td class="px-4 py-3 text-right text-xs text-muted-foreground">
                  {relTime(vm.started_at)}
                </td>
              </tr>
            {/each}
            {#if filteredVms.length === 0}
              <tr>
                <td colspan="6" class="px-4 py-8 text-center text-sm text-muted-foreground">
                  No active VMs.
                </td>
              </tr>
            {/if}
          </tbody>
        </table>
      </Card>
    </Tabs.Content>

    <!-- Nodes -->
    <Tabs.Content value="nodes">
      <Card class="overflow-hidden">
        <table class="w-full">
          <thead class="border-b border-border bg-muted/30">
            <tr class="text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <th class="px-4 py-3">Node</th>
              <th class="px-4 py-3">Status</th>
              <th class="px-4 py-3">CPU</th>
              <th class="px-4 py-3">Memory</th>
              <th class="px-4 py-3 text-right">Pods</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            {#each data.nodes as n (n.name)}
              <tr class="text-sm transition-colors hover:bg-muted/30">
                <td class="px-4 py-3 font-mono text-xs">{n.name}</td>
                <td class="px-4 py-3">
                  <Badge variant={n.ready ? 'success' : 'destructive'}>
                    <span
                      class={`size-1.5 rounded-full ${n.ready ? 'bg-success' : 'bg-destructive'}`}
                    ></span>
                    {n.ready ? 'Ready' : 'Not ready'}
                  </Badge>
                </td>
                <td class="px-4 py-3 text-xs text-muted-foreground">
                  {n.cpu_allocatable} / {n.cpu_capacity}
                </td>
                <td class="px-4 py-3 text-xs text-muted-foreground">
                  {fmtMem(n.memory_allocatable)} / {fmtMem(n.memory_capacity)}
                </td>
                <td class="px-4 py-3 text-right font-medium">{n.pod_count}</td>
              </tr>
            {/each}
            {#if data.nodes.length === 0}
              <tr>
                <td colspan="5" class="px-4 py-10 text-center text-sm text-muted-foreground">
                  <HardDrive class="mx-auto mb-2 size-5 opacity-50" />
                  No nodes are reporting yet.
                </td>
              </tr>
            {/if}
          </tbody>
        </table>
      </Card>
    </Tabs.Content>

    <!-- Audit -->
    <Tabs.Content value="audit">
      <Card class="overflow-hidden">
        <table class="w-full">
          <thead class="border-b border-border bg-muted/30">
            <tr class="text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <th class="px-4 py-3">Time</th>
              <th class="px-4 py-3">Action</th>
              <th class="px-4 py-3">Resource</th>
              <th class="px-4 py-3">User</th>
              <th class="px-4 py-3">IP</th>
              <th class="px-4 py-3 text-right">Status</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            {#each data.auditLogs as log (log.id)}
              <tr class="text-sm transition-colors hover:bg-muted/30">
                <td class="px-4 py-3 text-xs text-muted-foreground">
                  {relTime(log.created_at)}
                </td>
                <td class="px-4 py-3 font-medium">{log.action}</td>
                <td class="px-4 py-3 text-xs text-muted-foreground">
                  {#if log.resource_type}
                    <span>{log.resource_type}</span>
                    {#if log.resource_id}
                      <span class="ml-1 font-mono">{shortId(log.resource_id, 8)}</span>
                    {/if}
                  {:else}
                    —
                  {/if}
                </td>
                <td class="px-4 py-3 font-mono text-xs">
                  {log.user_id ? shortId(log.user_id, 8) : '—'}
                </td>
                <td class="px-4 py-3 font-mono text-xs text-muted-foreground">
                  {log.ip_address ?? '—'}
                </td>
                <td class={`px-4 py-3 text-right font-mono text-xs ${statusTone(log.status_code)}`}>
                  {log.status_code ?? '—'}
                </td>
              </tr>
            {/each}
            {#if data.auditLogs.length === 0}
              <tr>
                <td colspan="6" class="px-4 py-10 text-center text-sm text-muted-foreground">
                  No audit events recorded yet.
                </td>
              </tr>
            {/if}
          </tbody>
        </table>
      </Card>
    </Tabs.Content>
  </Tabs.Root>
</div>

<!-- Allocate credits dialog -->
<Dialog
  bind:open={allocOpen}
  title="Allocate credits"
  description={allocUser
    ? `to ${allocUser.name || allocUser.email}`
    : ''}
>
  <div class="space-y-4">
    <div>
      <Label for="alloc-amount">Amount</Label>
      <div class="relative mt-1">
        <Coins
          class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          id="alloc-amount"
          type="number"
          step="0.5"
          min="0.5"
          bind:value={allocAmount}
          class="pl-8"
        />
      </div>
      <p class="mt-1 text-xs text-muted-foreground">
        1 credit ≈ 1 hour of a "small" plan VM.
      </p>
    </div>
    <div>
      <Label for="alloc-desc">Description</Label>
      <Input
        id="alloc-desc"
        bind:value={allocDescription}
        placeholder="What is this for?"
        class="mt-1"
      />
    </div>
  </div>

  {#snippet footer()}
    <Button variant="outline" onclick={() => (allocOpen = false)}>Cancel</Button>
    <Button onclick={allocate} disabled={allocating}>
      {#if allocating}
        <Loader2 class="size-4 animate-spin" /> Allocating…
      {:else}
        <Coins class="size-4" /> Allocate
      {/if}
    </Button>
  {/snippet}
</Dialog>
