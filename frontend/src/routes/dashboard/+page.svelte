<script lang="ts">
  import {
    Coins,
    Server,
    History,
    Cpu,
    Plus,
    ArrowUpRight,
    ArrowDownRight,
    Activity,
    Sparkles
  } from 'lucide-svelte';
  import type { Pod, CreditTransaction, User } from '$lib/types';
  import {
    Button,
    Card,
    CardHeader,
    CardTitle,
    CardContent,
    Badge,
    Separator
  } from '$lib/ui';
  import PodCard from '$lib/components/PodCard.svelte';
  import StatCard from '$lib/components/StatCard.svelte';
  import UsageTrend from '$lib/components/UsageTrend.svelte';
  import { relTime, formatBytes } from '$lib/utils';

  type Summary = {
    pod_count: number;
    avg_cpu_percent: number;
    avg_memory_bytes: number;
  };

  let {
    data
  }: {
    data: {
      balance: number;
      pods: Pod[];
      recent: CreditTransaction[];
      summary: Summary;
      user?: User | null;
    };
  } = $props();

  const activePods = $derived(
    data.pods.filter((p) => ['running', 'pending', 'creating'].includes(p.state))
  );
  const recentInactive = $derived(
    data.pods
      .filter((p) => !['running', 'pending', 'creating'].includes(p.state))
      .slice(0, 3)
  );

  function prettyTxType(t: string): string {
    if (t.startsWith('vm_usage')) return 'VM usage';
    if (t.startsWith('vm_prorate')) return 'Final charge';
    if (t === 'allocation' || t.startsWith('allocate')) return 'Allocation';
    return t.replaceAll('_', ' ');
  }
</script>

<div class="space-y-8">
  <!-- Hero -->
  <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
    <div>
      <div
        class="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs font-medium text-muted-foreground"
      >
        <Sparkles class="size-3 text-primary" />
        Welcome back
      </div>
      <h1 class="mt-2 text-3xl font-bold tracking-tight">Dashboard</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Manage your virtual machines, monitor usage, and track credit spend.
      </p>
    </div>
    <Button href="/pods" size="lg">
      <Plus class="size-4" /> Launch a VM
    </Button>
  </div>

  <!-- Stats -->
  <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
    <StatCard
      label="Credit balance"
      value={data.balance.toFixed(1)}
      sub="credits remaining"
      icon={Coins}
      tone={data.balance > 50 ? 'success' : data.balance > 10 ? 'warning' : 'destructive'}
      href="/credits"
    />
    <StatCard
      label="Active VMs"
      value={activePods.length}
      sub="of 3 max concurrent"
      icon={Server}
      tone="primary"
      href="/pods"
    />
    <StatCard
      label="Avg CPU (24h)"
      value={`${data.summary.avg_cpu_percent.toFixed(1)}%`}
      sub={data.summary.pod_count
        ? `across ${data.summary.pod_count} VM${data.summary.pod_count === 1 ? '' : 's'}`
        : 'no activity yet'}
      icon={Cpu}
      tone="info"
    />
    <StatCard
      label="Avg memory (24h)"
      value={formatBytes(data.summary.avg_memory_bytes ?? 0)}
      sub="rolling average"
      icon={Activity}
      tone="default"
    />
  </div>

  <!-- Usage trend -->
  <UsageTrend />

  <!-- Active VMs -->
  <section>
    <div class="mb-3 flex items-end justify-between">
      <div>
        <h2 class="text-lg font-semibold tracking-tight">Active VMs</h2>
        <p class="text-sm text-muted-foreground">
          Currently running, pending, or starting up.
        </p>
      </div>
      {#if activePods.length > 0}
        <Button href="/pods" variant="ghost" size="sm">
          Manage all <ArrowUpRight class="size-4" />
        </Button>
      {/if}
    </div>

    {#if activePods.length === 0}
      <Card class="border-dashed bg-muted/20">
        <CardContent class="flex flex-col items-center gap-3 py-12 text-center">
          <div
            class="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary"
          >
            <Server class="size-5" />
          </div>
          <div>
            <p class="font-medium">No active VMs right now</p>
            <p class="mt-1 text-sm text-muted-foreground">
              Spin up a fresh VM in seconds — choose a plan and template.
            </p>
          </div>
          <Button href="/pods">
            <Plus class="size-4" /> Launch your first VM
          </Button>
        </CardContent>
      </Card>
    {:else}
      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {#each activePods as pod (pod.id)}
          <PodCard {pod} href="/pods/{pod.id}" />
        {/each}
      </div>
    {/if}
  </section>

  <div class="grid gap-6 lg:grid-cols-5">
    <!-- Recent VMs -->
    <section class="lg:col-span-3">
      <div class="mb-3 flex items-end justify-between">
        <h2 class="text-lg font-semibold tracking-tight">Recent VMs</h2>
        {#if data.pods.length > 0}
          <Button href="/pods" variant="ghost" size="sm">All VMs</Button>
        {/if}
      </div>
      {#if recentInactive.length === 0}
        <Card class="border-dashed">
          <CardContent class="py-8 text-center text-sm text-muted-foreground">
            Your past VMs will appear here.
          </CardContent>
        </Card>
      {:else}
        <div class="grid gap-4 sm:grid-cols-2">
          {#each recentInactive as pod (pod.id)}
            <PodCard {pod} href="/pods/{pod.id}" />
          {/each}
        </div>
      {/if}
    </section>

    <!-- Recent activity -->
    <section class="lg:col-span-2">
      <div class="mb-3 flex items-end justify-between">
        <h2 class="text-lg font-semibold tracking-tight">Recent activity</h2>
        <Button href="/credits" variant="ghost" size="sm">All</Button>
      </div>
      <Card>
        <CardHeader class="flex-row items-center gap-2 pb-3">
          <History class="size-4 text-muted-foreground" />
          <CardTitle class="text-sm">Last 5 transactions</CardTitle>
        </CardHeader>
        <Separator />
        <CardContent class="p-0">
          {#if data.recent.length === 0}
            <p class="px-6 py-6 text-sm text-muted-foreground">
              No transactions yet.
            </p>
          {:else}
            <ul class="divide-y divide-border">
              {#each data.recent as tx (tx.id)}
                <li class="flex items-center gap-3 px-4 py-3">
                  <span
                    class="flex size-8 items-center justify-center rounded-full"
                    class:bg-success-foreground={false}
                    class:bg-success={false}
                    class:text-success={tx.direction === 'credit'}
                    class:bg-destructive={false}
                    class:text-destructive={tx.direction === 'debit'}
                  >
                    {#if tx.direction === 'credit'}
                      <ArrowDownRight class="size-4" />
                    {:else}
                      <ArrowUpRight class="size-4" />
                    {/if}
                  </span>
                  <div class="min-w-0 flex-1">
                    <div class="text-sm font-medium truncate">
                      {prettyTxType(tx.type)}
                    </div>
                    <div class="text-xs text-muted-foreground">
                      {relTime(tx.created_at)}
                    </div>
                  </div>
                  <Badge
                    variant={tx.direction === 'credit' ? 'success' : 'muted'}
                    class="tabular-nums"
                  >
                    {tx.direction === 'credit' ? '+' : '−'}{tx.amount.toFixed(2)}
                  </Badge>
                </li>
              {/each}
            </ul>
          {/if}
        </CardContent>
      </Card>
    </section>
  </div>
</div>
