<script lang="ts">
  import {
    Users,
    Server,
    Database,
    Activity,
    Coins,
    Search,
    Loader2,
    ShieldAlert,
    HardDrive,
    Cpu,
    MemoryStick,
    ScrollText,
    ArrowRight
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
    Table,
    Tooltip,
    Dialog,
    Progress,
    Separator
  } from '$lib/ui';
  import StatCard from '$lib/components/StatCard.svelte';
  import SectionHeader from '$lib/components/SectionHeader.svelte';
  import PageTitle from '$lib/components/PageTitle.svelte';
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

  // Small icon-chip tone for the activity feed, derived from the status code.
  function activityTone(code: number | null | undefined): {
    dot: string;
    chip: string;
  } {
    if (code && code >= 500)
      return { dot: 'bg-destructive', chip: 'bg-destructive/10 text-destructive' };
    if (code && code >= 400)
      return { dot: 'bg-warning', chip: 'bg-warning/10 text-warning' };
    return { dot: 'bg-success', chip: 'bg-success/10 text-success' };
  }
</script>

<div class="space-y-8">
  <PageTitle
    title="Admin"
    eyebrow="Admin console"
    eyebrowIcon={ShieldAlert}
    description="Platform overview, user management, and audit trail."
  />

  <!-- Stats -->
  <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
    <StatCard
      label="Total users"
      value={data.stats.total_users}
      icon={Users}
      tone="primary"
      class="animate-fade-up"
    />
    <StatCard
      label="Active VMs"
      value={data.stats.active_vms}
      icon={Server}
      tone="success"
      class="animate-fade-up [animation-delay:70ms]"
    />
    <StatCard
      label="VMs all-time"
      value={data.stats.total_vms_created}
      icon={Database}
      tone="info"
      class="animate-fade-up [animation-delay:140ms]"
    />
    <StatCard
      label="Compute nodes"
      value={data.nodes.length}
      sub={`${data.nodes.filter((n) => n.ready).length} ready`}
      icon={Activity}
      tone={data.nodes.every((n) => n.ready) ? 'success' : 'warning'}
      class="animate-fade-up [animation-delay:210ms]"
    />
  </div>

  <!-- Tabs -->
  <Tabs.Root bind:value={tab}>
    <Tabs.List
      class="flex w-full max-w-full justify-start overflow-x-auto [scrollbar-width:none] sm:w-auto [&::-webkit-scrollbar]:hidden"
    >
      <Tabs.Trigger value="overview"><Activity /> Overview</Tabs.Trigger>
      <Tabs.Trigger value="users"><Users /> Users</Tabs.Trigger>
      <Tabs.Trigger value="vms"><Server /> Active VMs</Tabs.Trigger>
      <Tabs.Trigger value="nodes"><HardDrive /> Nodes</Tabs.Trigger>
      <Tabs.Trigger value="audit"><ScrollText /> Audit log</Tabs.Trigger>
    </Tabs.List>

    <!-- Overview -->
    <Tabs.Content value="overview">
      <div class="grid gap-4 lg:grid-cols-2">
        <Card class="animate-fade-up">
          <CardContent class="space-y-3 pt-6">
            <SectionHeader title="Recent activity" icon={Activity}>
              {#snippet action()}
                <button
                  type="button"
                  onclick={() => (tab = 'audit')}
                  class="group inline-flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                >
                  View all
                  <ArrowRight class="size-3 transition-transform group-hover:translate-x-0.5" />
                </button>
              {/snippet}
            </SectionHeader>
            <Separator />
            {#if data.auditLogs.length === 0}
              <div class="flex flex-col items-center gap-2 py-10 text-center">
                <span class="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <ScrollText class="size-5" />
                </span>
                <p class="text-sm text-muted-foreground">No events yet.</p>
              </div>
            {:else}
              <ul class="-mx-2 space-y-0.5">
                {#each data.auditLogs.slice(0, 7) as log (log.id)}
                  {@const tone = activityTone(log.status_code)}
                  <li
                    class="flex items-center gap-3 rounded-lg px-2 py-2 text-sm transition-colors hover:bg-muted/50"
                  >
                    <span
                      class={`flex size-7 shrink-0 items-center justify-center rounded-lg ${tone.chip}`}
                    >
                      <span class={`size-2 rounded-full ${tone.dot}`}></span>
                    </span>
                    <div class="min-w-0 flex-1">
                      <div class="truncate font-medium">{log.action}</div>
                      {#if log.resource_type}
                        <div class="truncate text-xs text-muted-foreground">
                          {log.resource_type}{log.resource_id ? ` · ${shortId(log.resource_id, 8)}` : ''}
                        </div>
                      {/if}
                    </div>
                    <span class="shrink-0 text-xs tabular-nums text-muted-foreground">
                      {relTime(log.created_at)}
                    </span>
                  </li>
                {/each}
              </ul>
            {/if}
          </CardContent>
        </Card>

        <Card class="animate-fade-up [animation-delay:80ms]">
          <CardContent class="space-y-4 pt-6">
            <SectionHeader title="Cluster pressure" icon={Server} />
            <Separator />
            {#if data.nodes.length === 0}
              <div class="flex flex-col items-center gap-2 py-10 text-center">
                <span class="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <HardDrive class="size-5" />
                </span>
                <p class="text-sm text-muted-foreground">No nodes reporting.</p>
              </div>
            {:else}
              {@const totalCpu = data.nodes.reduce((a, n) => a + (parseFloat(n.cpu_capacity) || 0), 0)}
              {@const allocCpu = data.nodes.reduce((a, n) => a + (parseFloat(n.cpu_allocatable) || 0), 0)}
              {@const totalMem = data.nodes.reduce((a, n) => a + (memoryToGb(n.memory_capacity) || 0), 0)}
              {@const allocMem = data.nodes.reduce((a, n) => a + (memoryToGb(n.memory_allocatable) || 0), 0)}
              {@const cpuUsedPct = totalCpu ? ((totalCpu - allocCpu) / totalCpu) * 100 : 0}
              {@const memUsedPct = totalMem ? ((totalMem - allocMem) / totalMem) * 100 : 0}
              <div class="rounded-xl border border-border/60 bg-muted/20 p-3.5">
                <div class="mb-2 flex items-baseline justify-between text-sm">
                  <span class="flex items-center gap-1.5 font-medium">
                    <Cpu class="size-3.5 text-primary" /> CPU reserved
                  </span>
                  <span class="font-semibold tabular-nums">{cpuUsedPct.toFixed(0)}%</span>
                </div>
                <Progress value={cpuUsedPct} indicatorClass="bg-gradient-to-r from-primary to-info" />
                <p class="mt-1.5 text-xs text-muted-foreground">
                  {(totalCpu - allocCpu).toFixed(1)} of {totalCpu.toFixed(1)} cores reserved
                </p>
              </div>
              <div class="rounded-xl border border-border/60 bg-muted/20 p-3.5">
                <div class="mb-2 flex items-baseline justify-between text-sm">
                  <span class="flex items-center gap-1.5 font-medium">
                    <MemoryStick class="size-3.5 text-info" /> Memory reserved
                  </span>
                  <span class="font-semibold tabular-nums">{memUsedPct.toFixed(0)}%</span>
                </div>
                <Progress value={memUsedPct} indicatorClass="bg-gradient-to-r from-info to-primary" />
                <p class="mt-1.5 text-xs text-muted-foreground">
                  {(totalMem - allocMem).toFixed(1)} of {totalMem.toFixed(1)} GB reserved
                </p>
              </div>
              <div class="flex items-center justify-between rounded-xl border border-border/60 bg-muted/20 px-3.5 py-2.5 text-sm">
                <span class="flex items-center gap-1.5 font-medium">
                  <Activity class="size-3.5 text-success" /> Nodes ready
                </span>
                <Badge variant={data.nodes.every((n) => n.ready) ? 'success' : 'warning'}>
                  {data.nodes.filter((n) => n.ready).length} / {data.nodes.length}
                </Badge>
              </div>
            {/if}
          </CardContent>
        </Card>
      </div>
    </Tabs.Content>

    <!-- Users -->
    <Tabs.Content value="users">
      <div class="animate-fade-up space-y-3">
        <SectionHeader title="Users" icon={Users} description={`${data.users.length} registered`}>
          {#snippet action()}
            <div class="relative">
              <Search
                class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                type="search"
                placeholder="Search users…"
                bind:value={userQuery}
                class="h-9 w-40 pl-8 sm:w-64"
              />
            </div>
          {/snippet}
        </SectionHeader>

        <Card class="overflow-hidden">
          <Table.Root>
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head>User</Table.Head>
                <Table.Head class="hidden md:table-cell">Email</Table.Head>
                <Table.Head>Role</Table.Head>
                <Table.Head class="hidden sm:table-cell">Joined</Table.Head>
                <Table.Head class="text-right">Actions</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {#each filteredUsers as u (u.id)}
                <Table.Row class="group">
                  <Table.Cell>
                    <div class="flex items-center gap-2.5">
                      <Avatar name={u.name || u.email} class="size-8 ring-1 ring-border/60" />
                      <div class="min-w-0">
                        <div class="truncate font-medium">{u.name || '—'}</div>
                        <div class="truncate text-xs text-muted-foreground md:hidden">{u.email}</div>
                      </div>
                    </div>
                  </Table.Cell>
                  <Table.Cell class="hidden text-muted-foreground md:table-cell">{u.email}</Table.Cell>
                  <Table.Cell>
                    {#if data.currentUserRole === 'admin' && u.id !== data.currentUserId}
                      <select
                        class="rounded-md border border-border bg-background px-2 py-1 text-xs font-medium capitalize transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
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
                  </Table.Cell>
                  <Table.Cell class="hidden text-muted-foreground sm:table-cell">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                  </Table.Cell>
                  <Table.Cell class="text-right">
                    <Tooltip content="Allocate credits to this user">
                      <Button
                        variant="outline"
                        size="sm"
                        class="opacity-70 transition-opacity group-hover:opacity-100"
                        onclick={() => openAlloc(u)}
                      >
                        <Coins class="size-3.5" /> Allocate
                      </Button>
                    </Tooltip>
                  </Table.Cell>
                </Table.Row>
              {/each}
              {#if filteredUsers.length === 0}
                <Table.Row class="hover:bg-transparent">
                  <Table.Cell colspan={5} class="py-10 text-center text-sm text-muted-foreground">
                    No users match your search.
                  </Table.Cell>
                </Table.Row>
              {/if}
            </Table.Body>
          </Table.Root>
        </Card>
      </div>
    </Tabs.Content>

    <!-- Active VMs -->
    <Tabs.Content value="vms">
      <div class="animate-fade-up space-y-3">
        <SectionHeader title="Active VMs" icon={Server} description={`${data.activeVms.length} running`}>
          {#snippet action()}
            <div class="relative">
              <Search
                class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                type="search"
                placeholder="Search VMs or owners…"
                bind:value={vmQuery}
                class="h-9 w-40 pl-8 sm:w-64"
              />
            </div>
          {/snippet}
        </SectionHeader>

        <Card class="overflow-hidden">
          <Table.Root>
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head>VM</Table.Head>
                <Table.Head>Owner</Table.Head>
                <Table.Head class="hidden sm:table-cell">Plan</Table.Head>
                <Table.Head class="hidden lg:table-cell">Resources</Table.Head>
                <Table.Head>State</Table.Head>
                <Table.Head class="text-right">Started</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {#each filteredVms as vm (vm.id)}
                <Table.Row class="group">
                  <Table.Cell class="font-mono text-xs">{shortId(vm.id, 10)}</Table.Cell>
                  <Table.Cell>
                    <div class="flex items-center gap-2">
                      <Avatar name={vm.user_name || vm.user_email} class="size-7 ring-1 ring-border/60" />
                      <div class="min-w-0">
                        <div class="truncate font-medium">{vm.user_name ?? '—'}</div>
                        <div class="truncate text-xs text-muted-foreground">
                          {vm.user_email ?? ''}
                        </div>
                      </div>
                    </div>
                  </Table.Cell>
                  <Table.Cell class="hidden capitalize sm:table-cell">{vm.plan}</Table.Cell>
                  <Table.Cell class="hidden text-xs text-muted-foreground lg:table-cell">
                    {vm.cpu ?? '—'} CPU · {vm.memory ?? '—'}
                  </Table.Cell>
                  <Table.Cell>
                    <Badge variant={stateBadge[vm.state] ?? 'muted'} class="capitalize">
                      {vm.state}
                    </Badge>
                  </Table.Cell>
                  <Table.Cell class="text-right text-xs text-muted-foreground">
                    {relTime(vm.started_at)}
                  </Table.Cell>
                </Table.Row>
              {/each}
              {#if filteredVms.length === 0}
                <Table.Row class="hover:bg-transparent">
                  <Table.Cell colspan={6} class="py-12 text-center text-sm text-muted-foreground">
                    <Server class="mx-auto mb-2 size-5 opacity-50" />
                    No active VMs.
                  </Table.Cell>
                </Table.Row>
              {/if}
            </Table.Body>
          </Table.Root>
        </Card>
      </div>
    </Tabs.Content>

    <!-- Nodes -->
    <Tabs.Content value="nodes">
      <div class="animate-fade-up space-y-3">
        <SectionHeader
          title="Compute nodes"
          icon={HardDrive}
          description={`${data.nodes.filter((n) => n.ready).length} of ${data.nodes.length} ready`}
        />
        <Card class="overflow-hidden">
          <Table.Root>
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head>Node</Table.Head>
                <Table.Head>Status</Table.Head>
                <Table.Head class="hidden sm:table-cell">CPU</Table.Head>
                <Table.Head class="hidden sm:table-cell">Memory</Table.Head>
                <Table.Head class="text-right">Pods</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {#each data.nodes as n (n.name)}
                <Table.Row class="group">
                  <Table.Cell>
                    <div class="flex items-center gap-2.5">
                      <span
                        class={`flex size-8 shrink-0 items-center justify-center rounded-lg transition-transform group-hover:scale-105 ${n.ready ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}
                      >
                        <HardDrive class="size-4" />
                      </span>
                      <span class="font-mono text-xs">{n.name}</span>
                    </div>
                  </Table.Cell>
                  <Table.Cell>
                    <Badge variant={n.ready ? 'success' : 'destructive'}>
                      <span
                        class={`size-1.5 rounded-full ${n.ready ? 'bg-success' : 'bg-destructive'}`}
                      ></span>
                      {n.ready ? 'Ready' : 'Not ready'}
                    </Badge>
                  </Table.Cell>
                  <Table.Cell class="hidden text-xs text-muted-foreground sm:table-cell">
                    {n.cpu_allocatable} / {n.cpu_capacity}
                  </Table.Cell>
                  <Table.Cell class="hidden text-xs text-muted-foreground sm:table-cell">
                    {fmtMem(n.memory_allocatable)} / {fmtMem(n.memory_capacity)}
                  </Table.Cell>
                  <Table.Cell class="text-right font-medium tabular-nums">{n.pod_count}</Table.Cell>
                </Table.Row>
              {/each}
              {#if data.nodes.length === 0}
                <Table.Row class="hover:bg-transparent">
                  <Table.Cell colspan={5} class="py-12 text-center text-sm text-muted-foreground">
                    <HardDrive class="mx-auto mb-2 size-5 opacity-50" />
                    No nodes are reporting yet.
                  </Table.Cell>
                </Table.Row>
              {/if}
            </Table.Body>
          </Table.Root>
        </Card>
      </div>
    </Tabs.Content>

    <!-- Audit -->
    <Tabs.Content value="audit">
      <div class="animate-fade-up space-y-3">
        <SectionHeader
          title="Audit log"
          icon={ScrollText}
          description={`${data.auditLogs.length} recorded event${data.auditLogs.length === 1 ? '' : 's'}`}
        />
        <Card class="overflow-hidden">
          <Table.Root>
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head>Time</Table.Head>
                <Table.Head>Action</Table.Head>
                <Table.Head class="hidden md:table-cell">Resource</Table.Head>
                <Table.Head class="hidden lg:table-cell">User</Table.Head>
                <Table.Head class="hidden lg:table-cell">IP</Table.Head>
                <Table.Head class="text-right">Status</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {#each data.auditLogs as log (log.id)}
                <Table.Row class="group">
                  <Table.Cell class="whitespace-nowrap text-xs text-muted-foreground">
                    {relTime(log.created_at)}
                  </Table.Cell>
                  <Table.Cell class="font-medium">{log.action}</Table.Cell>
                  <Table.Cell class="hidden text-xs text-muted-foreground md:table-cell">
                    {#if log.resource_type}
                      <span>{log.resource_type}</span>
                      {#if log.resource_id}
                        <span class="ml-1 font-mono">{shortId(log.resource_id, 8)}</span>
                      {/if}
                    {:else}
                      —
                    {/if}
                  </Table.Cell>
                  <Table.Cell class="hidden font-mono text-xs lg:table-cell">
                    {log.user_id ? shortId(log.user_id, 8) : '—'}
                  </Table.Cell>
                  <Table.Cell class="hidden font-mono text-xs text-muted-foreground lg:table-cell">
                    {log.ip_address ?? '—'}
                  </Table.Cell>
                  <Table.Cell class="text-right">
                    <span
                      class={`inline-flex items-center rounded-md bg-muted/60 px-1.5 py-0.5 font-mono text-xs font-semibold ${statusTone(log.status_code)}`}
                    >
                      {log.status_code ?? '—'}
                    </span>
                  </Table.Cell>
                </Table.Row>
              {/each}
              {#if data.auditLogs.length === 0}
                <Table.Row class="hover:bg-transparent">
                  <Table.Cell colspan={6} class="py-12 text-center text-sm text-muted-foreground">
                    <ScrollText class="mx-auto mb-2 size-5 opacity-50" />
                    No audit events recorded yet.
                  </Table.Cell>
                </Table.Row>
              {/if}
            </Table.Body>
          </Table.Root>
        </Card>
      </div>
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
