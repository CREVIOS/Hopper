<script lang="ts">
  import {
    Coins,
    Server,
    Cpu,
    Plus,
    ArrowUpRight,
    ArrowDownRight,
    Activity,
    Sparkles,
    Clock
  } from 'lucide-svelte';
  import { VM_PLAN_INFO } from '$lib/types';
  import type { Pod, CreditTransaction, User } from '$lib/types';
  import {
    Button,
    Card,
    CardContent,
    Badge,
    Table
  } from '$lib/ui';
  import StatCard from '$lib/components/StatCard.svelte';
  import UsageTrend from '$lib/components/UsageTrend.svelte';
  import PageTitle from '$lib/components/PageTitle.svelte';
  import SectionHeader from '$lib/components/SectionHeader.svelte';
  import Donut from '$lib/components/Donut.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { goto } from '$app/navigation';
  import { relTime, formatBytes, shortId } from '$lib/utils';

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
  const activeBurnRate = $derived.by(() =>
    activePods.reduce((total, pod) => total + (VM_PLAN_INFO[pod.plan as keyof typeof VM_PLAN_INFO]?.rate ?? 0), 0)
  );
  const lowBalanceThreshold = 10;
  const showLowBalanceWarning = $derived(data.balance < lowBalanceThreshold);
  const estimatedRuntime = $derived.by(() => {
    if (activeBurnRate <= 0 || data.balance <= 0) return null;
    const hoursRemaining = data.balance / activeBurnRate;
    const totalMinutes = Math.max(1, Math.floor(hoursRemaining * 60));
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    if (hours > 0) return `About ${hours}h ${minutes}m left at the current burn rate`;
    return `About ${minutes}m left at the current burn rate`;
  });

  function prettyTxType(t: string): string {
    if (t.startsWith('vm_usage')) return 'VM usage';
    if (t.startsWith('vm_prorate')) return 'Final charge';
    if (t === 'allocation' || t.startsWith('allocate')) return 'Allocation';
    return t.replaceAll('_', ' ');
  }

  // The VM id embedded in the tx type ("vm_usage:<id>"), shortened for display.
  function shortPod(raw: string): string {
    const i = raw.indexOf(':');
    if (i < 0) return '';
    const id = raw.slice(i + 1);
    return id.startsWith('vm-') && id.length > 11 ? id.slice(0, 11) : id.slice(0, 8);
  }

  // Per-minute billing produces many identical tiny charges — collapse them into
  // one row per (kind · VM) with a running total and count, so the feed reads
  // cleanly instead of ten identical "−0.02" lines.
  type Grouped = { label: string; pod: string; direction: 'debit' | 'credit'; amount: number; count: number; when: string };
  const groupedRecent = $derived.by(() => {
    const map = new Map<string, Grouped>();
    for (const tx of data.recent) {
      const pod = shortPod(tx.type);
      const key = `${prettyTxType(tx.type)}|${pod}|${tx.direction}`;
      const g = map.get(key);
      if (g) {
        g.amount += tx.amount;
        g.count += 1;
      } else {
        map.set(key, { label: prettyTxType(tx.type), pod, direction: tx.direction, amount: tx.amount, count: 1, when: tx.created_at });
      }
    }
    return [...map.values()];
  });
</script>

<div class="space-y-6">
  <!-- Hero -->
  <PageTitle
    eyebrow="Welcome back"
    eyebrowIcon={Sparkles}
    title="Dashboard"
    description="Manage your virtual machines, monitor usage, and track credit spend."
  >
    {#snippet action()}
      <Button href="/pods" size="lg">
        <Plus class="size-4" /> Launch a VM
      </Button>
    {/snippet}
  </PageTitle>

  {#if data.user?.pending_teacher}
    <div
      class="flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/5 p-4"
    >
      <Clock class="mt-0.5 size-5 shrink-0 text-warning" />
      <div class="text-sm">
        <p class="font-medium text-foreground">Teacher account pending approval</p>
        <p class="mt-0.5 text-muted-foreground">
          Thanks for signing up as a teacher — an admin will review your request
          shortly. For now you have a student account: you can launch VMs, and
          allocating credits to students unlocks as soon as you're approved.
        </p>
      </div>
    </div>
  {/if}

  {#if showLowBalanceWarning}
    <div
      class="flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/5 p-4"
      role="status"
      aria-live="polite"
    >
      <Clock class="mt-0.5 size-5 shrink-0 text-warning" />
      <div class="text-sm">
        <p class="font-medium text-foreground">
          Low balance: {data.balance.toFixed(2)} credits remaining
        </p>
        <p class="mt-0.5 text-muted-foreground">
          {estimatedRuntime ?? 'Top up soon to avoid interruptions to your running VMs.'}
        </p>
      </div>
    </div>
  {/if}

  <!-- Stats -->
  <div class="animate-fade-up grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
    <StatCard
      compact
      label="Active VMs"
      value={activePods.length}
      sub="of 3 max concurrent"
      icon={Server}
      tone="primary"
      href="/pods"
    />
    <StatCard
      compact
      label="Credit balance"
      value={data.balance.toFixed(1)}
      sub="credits remaining"
      icon={Coins}
      tone={data.balance > 50 ? 'success' : data.balance > 10 ? 'warning' : 'destructive'}
      href="/credits"
    />
    <StatCard
      compact
      label="Avg CPU (24h)"
      value={`${data.summary.avg_cpu_percent.toFixed(1)}%`}
      sub={data.summary.pod_count
        ? `across ${data.summary.pod_count} VM${data.summary.pod_count === 1 ? '' : 's'}`
        : 'no activity yet'}
      icon={Cpu}
      tone="info"
    />
    <StatCard
      compact
      label="Avg memory (24h)"
      value={formatBytes(data.summary.avg_memory_bytes ?? 0)}
      sub="rolling average"
      icon={Activity}
      tone="default"
    />
  </div>

  <!-- Usage trend + plan distribution -->
  <div class="animate-fade-up grid gap-4 lg:grid-cols-[1fr_340px]" style="animation-delay: 60ms">
    <UsageTrend />
    <Card class="p-5">
      <div class="mb-4">
        <h3 class="text-sm font-semibold">Plan distribution</h3>
        <p class="text-xs text-muted-foreground">Your VMs by plan</p>
      </div>
      <div class="flex items-center gap-5">
        <Donut
          segments={planSegments}
          size={132}
          thickness={15}
          centerValue={String(data.pods.length)}
          centerLabel="VMs"
        />
        <div class="min-w-0 flex-1 space-y-3">
          {#each planSegments as s (s.label)}
            <div class="flex items-center gap-2.5">
              <span class="size-2.5 shrink-0 rounded-full" style="background:{s.color}"></span>
              <span class="flex-1 text-sm font-medium capitalize">{s.label}</span>
              <span class="text-sm font-semibold tabular-nums text-muted-foreground">{s.value}</span>
            </div>
          {/each}
        </div>
      </div>
    </Card>
  </div>

  <!-- Your Virtual Machines -->
  <section class="animate-fade-up" style="animation-delay: 90ms">
    <SectionHeader
      class="mb-3"
      icon={Server}
      title="Your Virtual Machines"
      description="Every VM on your account."
    >
      {#snippet action()}
        <Button href="/pods" variant="ghost" size="sm">
          Manage all <ArrowUpRight class="size-4" />
        </Button>
      {/snippet}
    </SectionHeader>

    {#if data.pods.length === 0}
      <Card class="border-dashed bg-muted/20">
        <CardContent class="flex flex-col items-center gap-3 py-10 text-center">
          <div class="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Server class="size-5" />
          </div>
          <div>
            <p class="font-medium">No VMs yet</p>
            <p class="mt-1 text-sm text-muted-foreground">
              Spin up a fresh VM in seconds — choose a plan and template.
            </p>
          </div>
          <Button href="/pods"><Plus class="size-4" /> Launch your first VM</Button>
        </CardContent>
      </Card>
    {:else}
      <Card class="overflow-hidden">
        <Table.Root>
          <Table.Header class="bg-muted/40">
            <Table.Row class="hover:bg-transparent">
              <Table.Head>VM Name</Table.Head>
              <Table.Head>Plan</Table.Head>
              <Table.Head>Status</Table.Head>
              <Table.Head class="hidden sm:table-cell">Resources</Table.Head>
              <Table.Head class="hidden text-right md:table-cell">Created</Table.Head>
              <Table.Head class="w-10"><span class="sr-only">Open</span></Table.Head>
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {#each previewPods as pod (pod.id)}
              <Table.Row class="cursor-pointer" onclick={() => goto(`/pods/${pod.id}`)}>
                <Table.Cell>
                  <div class="flex items-center gap-3">
                    <span class="grid size-8 shrink-0 place-items-center rounded-lg bg-muted text-foreground">
                      <Server class="size-4" />
                    </span>
                    <div class="min-w-0">
                      <div class="font-mono text-sm font-semibold leading-tight">{shortId(pod.id, 10)}</div>
                      <div class="text-xs capitalize text-muted-foreground">{pod.plan} plan</div>
                    </div>
                  </div>
                </Table.Cell>
                <Table.Cell class="capitalize">{pod.plan}</Table.Cell>
                <Table.Cell><StatusBadge state={pod.state} /></Table.Cell>
                <Table.Cell class="hidden text-muted-foreground sm:table-cell">
                  {pod.cpu ?? '—'} vCPU · {pod.memory ?? '—'}
                </Table.Cell>
                <Table.Cell class="hidden whitespace-nowrap text-right text-xs text-muted-foreground md:table-cell">
                  {relTime(pod.created_at)}
                </Table.Cell>
                <Table.Cell><ArrowUpRight class="size-4 text-muted-foreground" /></Table.Cell>
              </Table.Row>
            {/each}
          </Table.Body>
        </Table.Root>
        {#if data.pods.length > previewPods.length}
          <div class="flex items-center justify-between border-t border-border bg-muted/30 px-4 py-2.5 text-xs text-muted-foreground">
            <span>Showing {previewPods.length} of {data.pods.length} VMs</span>
            <Button href="/pods" variant="ghost" size="sm" class="h-7 text-xs">
              View all <ArrowUpRight class="size-3.5" />
            </Button>
          </div>
        {/if}
      </Card>
    {/if}
  </section>

  <div class="space-y-6">
    <!-- Recent activity -->
    <section class="animate-fade-up" style="animation-delay: 150ms">
      <SectionHeader class="mb-3" icon={Coins} title="Recent activity">
        {#snippet action()}
          <Button href="/credits" variant="ghost" size="sm">All</Button>
        {/snippet}
      </SectionHeader>
      <Card class="overflow-hidden">
        {#if groupedRecent.length === 0}
          <CardContent class="py-10 text-center text-sm text-muted-foreground">
            No transactions yet.
          </CardContent>
        {:else}
          <Table.Root>
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head>Activity</Table.Head>
                <Table.Head class="hidden sm:table-cell">Source</Table.Head>
                <Table.Head class="w-28 text-right">When</Table.Head>
                <Table.Head class="w-28 text-right">Amount</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {#each groupedRecent as g (g.label + g.pod + g.direction)}
                <Table.Row class="group">
                  <Table.Cell>
                    <div class="flex min-w-0 items-center gap-3">
                      <span
                        class={`flex size-8 shrink-0 items-center justify-center rounded-full ring-1 ring-inset ${
                          g.direction === 'credit'
                            ? 'bg-success/15 text-success ring-success/20'
                            : 'bg-destructive/15 text-destructive ring-destructive/20'
                        }`}
                      >
                        {#if g.direction === 'credit'}
                          <ArrowDownRight class="size-4" />
                        {:else}
                          <ArrowUpRight class="size-4" />
                        {/if}
                      </span>
                      <div class="flex min-w-0 items-center gap-2">
                        <span class="truncate text-sm font-medium">{g.label}</span>
                        {#if g.count > 1}
                          <Badge variant="muted" class="px-1.5 py-0 text-[10px] tabular-nums">×{g.count}</Badge>
                        {/if}
                      </div>
                    </div>
                  </Table.Cell>
                  <Table.Cell class="hidden sm:table-cell">
                    {#if g.pod}
                      <span class="inline-flex items-center rounded-md border border-border/60 bg-muted/50 px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                        {g.pod}
                      </span>
                    {:else}
                      <span class="text-muted-foreground/40">·</span>
                    {/if}
                  </Table.Cell>
                  <Table.Cell class="w-28 whitespace-nowrap text-right text-xs text-muted-foreground">
                    {relTime(g.when)}
                  </Table.Cell>
                  <Table.Cell class="w-28 text-right">
                    <span
                      class={`inline-flex items-center rounded-full px-2 py-0.5 font-mono text-xs font-semibold tabular-nums ${
                        g.direction === 'debit'
                          ? 'bg-destructive/10 text-destructive'
                          : 'bg-success/10 text-success'
                      }`}
                    >
                      {g.direction === 'credit' ? '+' : '−'}{g.amount.toFixed(2)}
                    </span>
                  </Table.Cell>
                </Table.Row>
              {/each}
            </Table.Body>
          </Table.Root>
        {/if}
      </Card>
    </section>
  </div>
</div>
