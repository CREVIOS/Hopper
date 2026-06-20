<script lang="ts">
  import {
    Coins,
    TrendingDown,
    TrendingUp,
    Search,
    Calendar,
    History,
    ArrowUpRight,
    ArrowDownRight
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
    Badge,
    Separator
  } from '$lib/ui';
  import StatCard from '$lib/components/StatCard.svelte';
  import SpendChart from '$lib/components/SpendChart.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
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

  const bucketed = $derived.by(() => {
    const buckets: Record<Group, Row[]> = {
      today: [],
      yesterday: [],
      week: [],
      older: []
    };
    for (const r of filteredRows) buckets[groupOf(r.when)].push(r);
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
</script>

<div class="space-y-6">
  <PageHeader
    title="Credits"
    description="Your balance and how it's being spent."
  />

  <!-- Stats -->
  <div class="animate-fade-up grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
    <StatCard
      label="Available balance"
      value={data.balance.toFixed(2)}
      sub="credits"
      icon={Coins}
      tone={data.balance > 50
        ? 'success'
        : data.balance > 10
          ? 'warning'
          : 'destructive'}
    />
    <StatCard
      label="Spent on VMs"
      value={totals.vmSpend.toFixed(2)}
      sub="all-time"
      icon={TrendingDown}
      tone="destructive"
    />
    <StatCard
      label="Total received"
      value={totals.credited.toFixed(2)}
      sub="allocations & refunds"
      icon={TrendingUp}
      tone="success"
    />
  </div>

  <!-- Spend chart -->
  <Card class="animate-fade-up surface-glow overflow-hidden" style="animation-delay: 60ms">
    <CardHeader class="flex-row items-center justify-between">
      <CardTitle class="flex items-center gap-2 text-sm">
        <span
          class="flex size-6 items-center justify-center rounded-md bg-primary/10 text-primary"
        >
          <Calendar class="size-3.5" />
        </span>
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
    <CardContent class="pt-6">
      <SpendChart transactions={data.transactions} days={14} />
    </CardContent>
  </Card>

  <!-- Activity -->
  <section class="animate-fade-up" style="animation-delay: 90ms">
    <div class="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <h2 class="flex items-center gap-2 text-lg font-semibold tracking-tight">
        <span
          class="flex size-6 items-center justify-center rounded-md bg-primary/10 text-primary"
        >
          <History class="size-3.5" />
        </span>
        Activity
      </h2>
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
            No transactions yet — launch a VM to see usage here.
          {/if}
        </CardContent>
      </Card>
    {:else}
      <Card class="overflow-hidden">
        <!-- Fixed-height internal scroller: the list never grows the page,
             header stays pinned while you scroll through entries. -->
        <Table.Root containerClass="max-h-[30rem]">
          <Table.Header
            class="sticky top-0 z-10 bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80"
          >
            <Table.Row class="hover:bg-transparent">
              <Table.Head>Activity</Table.Head>
              <Table.Head class="hidden md:table-cell">Source</Table.Head>
              <Table.Head class="text-right">When</Table.Head>
              <Table.Head class="text-right">Amount</Table.Head>
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {#each ['today', 'yesterday', 'week', 'older'] as g (g)}
              {#if bucketed[g as Group].length > 0}
                <tr>
                  <td
                    colspan="4"
                    class="border-b border-border bg-muted/40 px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
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
                  <Table.Row>
                    <Table.Cell>
                      <div class="flex min-w-0 items-center gap-3">
                        <span
                          class={`flex size-8 shrink-0 items-center justify-center rounded-full ${
                            r.direction === 'credit'
                              ? 'bg-success/15 text-success'
                              : 'bg-destructive/15 text-destructive'
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
                            <Badge variant="muted" class="px-1.5 py-0 text-[10px]">
                              ×{r.count}
                            </Badge>
                          {/if}
                        </div>
                      </div>
                    </Table.Cell>
                    <Table.Cell class="hidden md:table-cell">
                      <span class="font-mono text-xs text-muted-foreground">
                        {r.sublabel || '—'}
                      </span>
                    </Table.Cell>
                    <Table.Cell class="text-right whitespace-nowrap">
                      <div class="text-xs text-muted-foreground">
                        {relTime(r.when)}
                      </div>
                      <div class="text-[11px] text-muted-foreground/70">
                        {r.when.toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </div>
                    </Table.Cell>
                    <Table.Cell class="text-right whitespace-nowrap">
                      <span
                        class={`font-mono text-sm font-semibold ${
                          r.direction === 'debit' ? 'text-destructive' : 'text-success'
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
        <div
          class="border-t border-border bg-muted/20 px-4 py-2 text-xs text-muted-foreground"
        >
          Showing {filteredRows.length} entr{filteredRows.length === 1 ? 'y' : 'ies'}
        </div>
      </Card>
    {/if}
  </section>
</div>
