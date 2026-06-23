<script lang="ts">
  import {
    Coins,
    TrendingDown,
    TrendingUp,
    Search,
    Calendar,
    History,
    ArrowUpRight,
    ArrowDownRight,
    Gauge,
    Receipt,
    Flame,
    CalendarClock,
    Scale
  } from 'lucide-svelte';
  import type { CreditTransaction } from '$lib/types';
  import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    Input,
    Tabs,
    Table,
    Pagination,
    Badge,
    Separator
  } from '$lib/ui';
  import StatCard from '$lib/components/StatCard.svelte';
  import SpendChart from '$lib/components/SpendChart.svelte';
  import PageTitle from '$lib/components/PageTitle.svelte';
  import { relTime } from '$lib/utils';

  let {
    data
  }: { data: { balance: number; transactions: CreditTransaction[] } } = $props();

  type Group = 'today' | 'yesterday' | 'week' | 'older';
  type Row = {
    label: string;
    sublabel: string;
    type: string;
    direction: 'debit' | 'credit';
    amount: number;
    when: Date;
    count: number;
    rawType: string;
    podId: string;
  };

  let query = $state('');
  let filter = $state<'all' | 'spend' | 'income'>('all');

  const PER_PAGE = 25;
  let page = $state(1);

  // Reset to the first page whenever the result set changes.
  $effect(() => {
    query;
    filter;
    page = 1;
  });

  function prettyType(raw: string): string {
    if (raw.startsWith('vm_usage')) return 'VM usage';
    if (raw.startsWith('vm_prorate')) return 'VM final charge';
    if (raw === 'allocation' || raw.startsWith('allocate')) return 'Credit allocation';
    if (raw.startsWith('refund')) return 'Refund';
    return raw.replaceAll('_', ' ');
  }

  function shortPod(raw: string): string {
    const idx = raw.indexOf(':');
    if (idx < 0) return '';
    const id = raw.slice(idx + 1);
    if (id.startsWith('vm-') && id.length > 11) return id.slice(0, 11);
    if (id.length > 12) return id.slice(0, 12);
    return id;
  }

  function groupOf(d: Date): Group {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const that = new Date(d);
    that.setHours(0, 0, 0, 0);
    const days = Math.round((today.getTime() - that.getTime()) / 86400000);
    if (days === 0) return 'today';
    if (days === 1) return 'yesterday';
    if (days < 7) return 'week';
    return 'older';
  }

  const groupTitle: Record<Group, string> = {
    today: 'Today',
    yesterday: 'Yesterday',
    week: 'Earlier this week',
    older: 'Earlier'
  };

  const rows = $derived.by(() => {
    const out: Row[] = [];
    const seen = new Map<string, Row>();
    for (const tx of data.transactions) {
      const when = new Date(tx.created_at);
      const minute = `${when.getFullYear()}-${when.getMonth()}-${when.getDate()}-${when.getHours()}-${when.getMinutes()}`;
      const key = `${tx.type}|${minute}|${tx.direction}`;
      const existing = seen.get(key);
      if (existing) {
        existing.amount += tx.amount;
        existing.count += 1;
        continue;
      }
      const podId = shortPod(tx.type);
      const row: Row = {
        label: prettyType(tx.type),
        sublabel: podId ? `Pod ${podId}` : '',
        type: tx.type,
        direction: tx.direction,
        amount: tx.amount,
        when,
        count: 1,
        rawType: tx.type,
        podId
      };
      seen.set(key, row);
      out.push(row);
    }
    return out;
  });

  const filteredRows = $derived.by(() => {
    let list = rows;
    if (filter === 'spend') list = list.filter((r) => r.direction === 'debit');
    else if (filter === 'income') list = list.filter((r) => r.direction === 'credit');
    const q = query.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (r) =>
          r.label.toLowerCase().includes(q) ||
          r.sublabel.toLowerCase().includes(q) ||
          r.podId.toLowerCase().includes(q)
      );
    }
    return list;
  });

  // Only the current page's rows are displayed; bucketing happens on that slice
  // so day-group headers still appear within the page.
  const pageRows = $derived(
    filteredRows.slice((page - 1) * PER_PAGE, page * PER_PAGE)
  );

  const bucketed = $derived.by(() => {
    const buckets: Record<Group, Row[]> = {
      today: [],
      yesterday: [],
      week: [],
      older: []
    };
    for (const r of pageRows) buckets[groupOf(r.when)].push(r);
    return buckets;
  });

  const totals = $derived.by(() => {
    let credited = 0;
    let debited = 0;
    let vmSpend = 0;
    for (const r of rows) {
      if (r.direction === 'credit') credited += r.amount;
      else {
        debited += r.amount;
        if (r.rawType.startsWith('vm_usage') || r.rawType.startsWith('vm_prorate'))
          vmSpend += r.amount;
      }
    }
    return { credited, debited, vmSpend };
  });

  // Extra figures derived from the same ledger — no new data sources.
  const spend14 = $derived.by(() => {
    const cutoff = Date.now() - 14 * 86400000;
    let s = 0;
    for (const r of rows)
      if (r.direction === 'debit' && r.when.getTime() >= cutoff) s += r.amount;
    return s;
  });
  const avgDaily = $derived(spend14 / 14);
  const txCount = $derived(rows.length);
  const net = $derived(totals.credited - totals.debited);
  const biggest = $derived.by(() => {
    let m = 0;
    for (const r of rows) if (r.direction === 'debit' && r.amount > m) m = r.amount;
    return m;
  });
  const activeDays = $derived.by(() => {
    const set = new Set<string>();
    for (const r of rows)
      set.add(`${r.when.getFullYear()}-${r.when.getMonth()}-${r.when.getDate()}`);
    return set.size;
  });

  // Tone for the balance hero — mirrors the StatCard thresholds used previously.
  const balanceTone = $derived(
    data.balance > 50 ? 'success' : data.balance > 10 ? 'warning' : 'destructive'
  );
  const toneText: Record<string, string> = {
    success: 'text-success',
    warning: 'text-warning',
    destructive: 'text-destructive'
  };
  const toneRail: Record<string, string> = {
    success: 'bg-success',
    warning: 'bg-warning',
    destructive: 'bg-destructive'
  };
  const toneGlow: Record<string, string> = {
    success: 'hsl(var(--success) / 0.10)',
    warning: 'hsl(var(--warning) / 0.10)',
    destructive: 'hsl(var(--destructive) / 0.12)'
  };
</script>

<div class="space-y-5">
  <PageTitle
    title="Credits"
    description="Your balance and how it's being spent."
  />

  <!-- Stat band: balance hero on the left, a 2×2 metric grid filling the right. -->
  <section class="animate-fade-up grid gap-4 lg:grid-cols-[1.05fr_1.4fr]">
    <div
      class="relative flex flex-col justify-between overflow-hidden rounded-2xl border border-border bg-card p-6"
      style="background-image: radial-gradient(110% 120% at 100% 0%, {toneGlow[balanceTone]} 0%, transparent 55%);"
    >
      <span class={`absolute inset-y-0 left-0 w-1 ${toneRail[balanceTone]} opacity-70`}></span>
      <div class="flex items-center justify-between">
        <p class="font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
          Available balance
        </p>
        <span class="grid size-9 place-items-center rounded-lg bg-muted/60 text-muted-foreground ring-1 ring-inset ring-border/60">
          <Coins class="size-4" strokeWidth={1.75} />
        </span>
      </div>
      <div class="mt-6 flex items-end gap-2.5">
        <span class={`font-mono text-5xl font-bold leading-none tracking-tight tabular-nums sm:text-[3.75rem] ${toneText[balanceTone]}`}>
          {data.balance.toFixed(2)}
        </span>
        <span class="pb-1 text-sm font-medium text-muted-foreground">credits</span>
      </div>
      <p class="mt-3 text-sm text-muted-foreground">
        {#if balanceTone === 'destructive'}
          Running low. Top up to keep your VMs alive.
        {:else if balanceTone === 'warning'}
          Getting low. Plan a top-up soon.
        {:else}
          Healthy balance for your active VMs.
        {/if}
      </p>
    </div>

    <div class="grid grid-cols-2 gap-3">
      <StatCard
        compact
        label="Spent on VMs"
        value={totals.vmSpend.toFixed(2)}
        sub="all-time"
        icon={TrendingDown}
        tone="destructive"
      />
      <StatCard
        compact
        label="Total received"
        value={totals.credited.toFixed(2)}
        sub="allocations & refunds"
        icon={TrendingUp}
        tone="success"
      />
      <StatCard
        compact
        label="Avg spend / day"
        value={avgDaily.toFixed(2)}
        sub="last 14 days"
        icon={Gauge}
        tone="warning"
      />
      <StatCard
        compact
        label="Transactions"
        value={txCount}
        sub="{activeDays} active day{activeDays === 1 ? '' : 's'}"
        icon={Receipt}
        tone="info"
      />
    </div>
  </section>

  <!-- Spend chart + at-a-glance figures, side by side to use the width. -->
  <section class="animate-fade-up grid gap-4 lg:grid-cols-[1.7fr_1fr]" style="animation-delay: 60ms">
    <Card class="surface-glow overflow-hidden">
      <CardHeader class="flex-row items-center justify-between px-5 py-4">
        <CardTitle class="flex items-center gap-2.5 text-sm font-semibold">
          <Calendar class="size-4 text-muted-foreground" strokeWidth={1.75} />
          Last 14 days
        </CardTitle>
        <div class="flex items-center gap-3 text-xs text-muted-foreground">
          <span class="inline-flex items-center gap-1.5">
            <span class="size-2 rounded-full bg-destructive/70"></span> Spent
          </span>
          <span class="inline-flex items-center gap-1.5">
            <span class="size-2 rounded-full bg-success/70"></span> Received
          </span>
        </div>
      </CardHeader>
      <Separator />
      <CardContent class="px-3 pb-3 pt-3">
        <SpendChart transactions={data.transactions} days={14} />
      </CardContent>
    </Card>

    <Card class="overflow-hidden">
      <CardHeader class="px-5 py-4">
        <CardTitle class="text-sm font-semibold">At a glance</CardTitle>
      </CardHeader>
      <Separator />
      <ul class="divide-y divide-border">
        {#each [
          { icon: Scale, label: 'Net change', value: `${net >= 0 ? '+' : '−'}${Math.abs(net).toFixed(2)}`, tint: net >= 0 ? 'text-success' : 'text-destructive' },
          { icon: TrendingDown, label: 'Spent (14 days)', value: spend14.toFixed(2), tint: 'text-foreground' },
          { icon: Flame, label: 'Biggest charge', value: biggest.toFixed(2), tint: 'text-foreground' },
          { icon: CalendarClock, label: 'Active days', value: String(activeDays), tint: 'text-foreground' }
        ] as row (row.label)}
          <li class="flex items-center justify-between gap-3 px-5 py-3 transition-colors hover:bg-muted/40">
            <span class="flex items-center gap-2.5 text-sm text-muted-foreground">
              <row.icon class="size-4 text-muted-foreground/70" strokeWidth={1.75} />
              {row.label}
            </span>
            <span class={`font-mono text-sm font-semibold tabular-nums ${row.tint}`}>{row.value}</span>
          </li>
        {/each}
      </ul>
    </Card>
  </section>

  <!-- Activity -->
  <section class="animate-fade-up" style="animation-delay: 90ms">
    <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-center gap-2.5">
        <History class="size-[1.15rem] text-muted-foreground" strokeWidth={1.75} />
        <h2 class="text-lg font-semibold tracking-tight">Activity</h2>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <div class="relative">
          <Search
            class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            placeholder="Search activity…"
            bind:value={query}
            class="h-9 w-56 pl-8"
          />
        </div>
        <Tabs.Root bind:value={filter}>
          <Tabs.List>
            <Tabs.Trigger value="all">All</Tabs.Trigger>
            <Tabs.Trigger value="spend">Spend</Tabs.Trigger>
            <Tabs.Trigger value="income">Income</Tabs.Trigger>
          </Tabs.List>
        </Tabs.Root>
      </div>
    </div>

    {#if filteredRows.length === 0}
      <Card class="border-dashed bg-muted/20">
        <CardContent class="py-12 text-center text-sm text-muted-foreground">
          {#if query || filter !== 'all'}
            No transactions match your filters.
          {:else}
            No transactions yet. Launch a VM to see usage here.
          {/if}
        </CardContent>
      </Card>
    {:else}
      <Card class="overflow-hidden">
        <!-- Fixed header lives OUTSIDE the scroll area so the scrollbar only
             spans the body, never the column names. Both tables use table-fixed
             + matching widths + a stable scrollbar gutter so columns line up. -->
        <Table.Root class="table-fixed" containerClass="[scrollbar-gutter:stable]">
          <Table.Header class="bg-muted/40">
            <Table.Row class="hover:bg-transparent">
              <Table.Head>Activity</Table.Head>
              <Table.Head class="hidden w-44 md:table-cell">Source</Table.Head>
              <Table.Head class="w-28 text-right">When</Table.Head>
              <Table.Head class="w-28 text-right">Amount</Table.Head>
            </Table.Row>
          </Table.Header>
        </Table.Root>
        <!-- Scrolling body: bounded height; paginated at {PER_PAGE}/page. -->
        <Table.Root
          class="table-fixed"
          containerClass="max-h-[34rem] [scrollbar-gutter:stable]"
        >
          <Table.Body>
            {#each ['today', 'yesterday', 'week', 'older'] as g (g)}
              {#if bucketed[g as Group].length > 0}
                <tr>
                  <td
                    colspan="4"
                    class="border-b border-border bg-muted/40 px-4 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground"
                  >
                    <span class="inline-flex items-center gap-2">
                      {groupTitle[g as Group]}
                      <Badge variant="muted" class="px-1.5 py-0 text-[10px]">
                        {bucketed[g as Group].length}
                      </Badge>
                    </span>
                  </td>
                </tr>
                {#each bucketed[g as Group] as r}
                  <Table.Row class="group">
                    <Table.Cell>
                      <div class="flex min-w-0 items-center gap-3">
                        <span
                          class={`flex size-8 shrink-0 items-center justify-center rounded-full ring-1 ring-inset transition-transform duration-200 group-hover:scale-110 ${
                            r.direction === 'credit'
                              ? 'bg-success/15 text-success ring-success/20'
                              : 'bg-destructive/15 text-destructive ring-destructive/20'
                          }`}
                        >
                          {#if r.direction === 'credit'}
                            <ArrowDownRight class="size-4" />
                          {:else}
                            <ArrowUpRight class="size-4" />
                          {/if}
                        </span>
                        <div class="flex min-w-0 items-center gap-2">
                          <span class="truncate text-sm font-medium">{r.label}</span>
                          {#if r.count > 1}
                            <Badge variant="muted" class="px-1.5 py-0 text-[10px] tabular-nums">
                              ×{r.count}
                            </Badge>
                          {/if}
                        </div>
                      </div>
                    </Table.Cell>
                    <Table.Cell class="hidden w-44 md:table-cell">
                      {#if r.sublabel}
                        <span
                          class="inline-flex max-w-full items-center truncate rounded-md border border-border/60 bg-muted/50 px-2 py-0.5 font-mono text-[11px] text-muted-foreground"
                        >
                          {r.sublabel}
                        </span>
                      {:else}
                        <span class="text-muted-foreground/40">·</span>
                      {/if}
                    </Table.Cell>
                    <Table.Cell class="w-28 text-right whitespace-nowrap">
                      <div class="text-xs font-medium text-muted-foreground">
                        {relTime(r.when)}
                      </div>
                      <div class="text-[11px] tabular-nums text-muted-foreground/60">
                        {r.when.toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </div>
                    </Table.Cell>
                    <Table.Cell class="w-28 text-right whitespace-nowrap">
                      <span
                        class={`inline-flex items-center rounded-full px-2 py-0.5 font-mono text-xs font-semibold tabular-nums ${
                          r.direction === 'debit'
                            ? 'bg-destructive/10 text-destructive'
                            : 'bg-success/10 text-success'
                        }`}
                      >
                        {r.direction === 'debit' ? '−' : '+'}{r.amount.toFixed(2)}
                      </span>
                    </Table.Cell>
                  </Table.Row>
                {/each}
              {/if}
            {/each}
          </Table.Body>
        </Table.Root>
        <div class="border-t border-border bg-muted/20 px-4 py-3">
          <Pagination
            count={filteredRows.length}
            perPage={PER_PAGE}
            bind:page
            itemLabel="entry"
          />
        </div>
      </Card>
    {/if}
  </section>
</div>
