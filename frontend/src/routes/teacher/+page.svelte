<script lang="ts">
  import { GraduationCap, Coins, Search, Wallet, Users } from 'lucide-svelte';
  import { invalidateAll } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import { Button, Card, Input, Label, Table, Dialog, Tooltip } from '$lib/ui';
  import StatCard from '$lib/components/StatCard.svelte';
  import SectionHeader from '$lib/components/SectionHeader.svelte';
  import PageTitle from '$lib/components/PageTitle.svelte';
  import Avatar from '$lib/ui/avatar.svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { api, ApiError } from '$lib/api/client';

  type Student = { id: string; email: string; name: string; balance: number };

  let { data }: { data: { balance: number; students: Student[]; currentUserId: string } } = $props();

  let query = $state('');
  const filtered = $derived(
    query
      ? data.students.filter(
          (s) =>
            s.email.toLowerCase().includes(query.toLowerCase()) ||
            (s.name ?? '').toLowerCase().includes(query.toLowerCase())
        )
      : data.students
  );

  // Allocation dialog
  let open = $state(false);
  let target = $state<Student | null>(null);
  let amount = $state(1);
  let description = $state('');
  let allocating = $state(false);

  function openAlloc(s: Student) {
    target = s;
    amount = 1;
    description = `Allocation for ${s.name || s.email}`;
    open = true;
  }

  async function allocate() {
    if (!target || allocating) return;
    if (!Number.isFinite(amount) || amount <= 0) {
      toast.error('Amount must be a positive number');
      return;
    }
    if (amount > data.balance) {
      toast.error('Not enough credits', {
        description: `You have ${data.balance.toFixed(2)}, tried to allocate ${amount}.`
      });
      return;
    }
    allocating = true;
    const id = toast.loading(`Allocating ${amount} credit${amount === 1 ? '' : 's'}…`);
    try {
      await api.post('/credits/allocate', {
        user_id: target.id,
        amount,
        description: description || 'teacher_allocation'
      });
      toast.success(`Allocated ${amount.toFixed(2)} credits`, {
        id,
        description: target.name || target.email
      });
      open = false;
      await invalidateAll();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Allocation failed';
      toast.error('Could not allocate credits', { id, description: msg });
    } finally {
      allocating = false;
    }
  }
</script>

<div class="space-y-8">
  <PageTitle
    title="Teaching"
    eyebrow="Teacher console"
    eyebrowIcon={GraduationCap}
    description="Allocate your credit budget to students. Your balance is funded by an admin."
  />

  <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
    <StatCard compact label="Your balance" value={data.balance.toFixed(2)} icon={Wallet} tone="primary" class="animate-fade-up" />
    <StatCard compact label="Students" value={data.students.length} icon={Users} tone="info" class="animate-fade-up [animation-delay:70ms]" />
    <StatCard
      compact
      label="Allocated (students)"
      value={data.students.reduce((a, s) => a + (s.balance || 0), 0).toFixed(2)}
      icon={Coins}
      tone="success"
      class="animate-fade-up [animation-delay:140ms]"
    />
  </div>

  <div class="animate-fade-up space-y-3">
    <SectionHeader title="Students" icon={Users}>
      {#snippet action()}
        <div class="relative">
          <Search class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input type="search" placeholder="Search students…" bind:value={query} class="h-9 w-40 pl-8 sm:w-64" />
        </div>
      {/snippet}
    </SectionHeader>

    {#if data.balance <= 0}
      <div class="rounded-lg border border-warning/30 bg-warning/5 p-3 text-sm text-warning">
        You have no credits yet. An admin needs to grant you a budget before you can allocate to students.
      </div>
    {/if}

    <Card class="overflow-hidden">
      <Table.Root class="table-fixed">
        <Table.Header class="bg-muted/40">
          <Table.Row class="hover:bg-transparent">
            <Table.Head>Student</Table.Head>
            <Table.Head class="hidden w-56 md:table-cell">Email</Table.Head>
            <Table.Head class="w-28 text-right">Balance</Table.Head>
            <Table.Head class="w-32 text-right">Actions</Table.Head>
          </Table.Row>
        </Table.Header>
        <Table.Body>
          {#each filtered as s (s.id)}
            <Table.Row class="group">
              <Table.Cell>
                <div class="flex items-center gap-2.5">
                  <Avatar name={s.name || s.email} class="size-8 shrink-0 ring-1 ring-border/60" />
                  <div class="min-w-0">
                    <div class="truncate font-medium">{s.name || '—'}</div>
                    <div class="truncate text-xs text-muted-foreground md:hidden">{s.email}</div>
                  </div>
                </div>
              </Table.Cell>
              <Table.Cell class="hidden w-56 truncate text-muted-foreground md:table-cell">{s.email}</Table.Cell>
              <Table.Cell class="w-28 text-right font-semibold tabular-nums">{(s.balance ?? 0).toFixed(2)}</Table.Cell>
              <Table.Cell class="w-32 text-right">
                <Tooltip content="Allocate credits to this student">
                  {#snippet children(props)}
                  <Button
                    {...props}
                    variant="outline"
                    size="sm"
                    class="opacity-70 transition-opacity group-hover:opacity-100"
                    onclick={() => openAlloc(s)}
                    disabled={data.balance <= 0}
                  >
                    <Coins class="size-3.5" /> Allocate
                  </Button>
                  {/snippet}
                </Tooltip>
              </Table.Cell>
            </Table.Row>
          {/each}
          {#if filtered.length === 0}
            <Table.Row class="hover:bg-transparent">
              <Table.Cell colspan={4} class="py-10 text-center text-sm text-muted-foreground">
                {data.students.length === 0 ? 'No students have signed up yet.' : 'No students match your search.'}
              </Table.Cell>
            </Table.Row>
          {/if}
        </Table.Body>
      </Table.Root>
    </Card>
  </div>
</div>

<Dialog bind:open title="Allocate credits" description={target ? `to ${target.name || target.email}` : ''}>
  <div class="space-y-4">
    <div>
      <Label for="t-amount">Amount</Label>
      <div class="relative mt-1">
        <Coins class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input id="t-amount" type="number" step="0.5" min="0.5" bind:value={amount} class="pl-8" />
      </div>
      <p class="mt-1 text-xs text-muted-foreground">
        You have {data.balance.toFixed(2)} credits. 1 credit ≈ 1 hour of a "small" VM.
      </p>
    </div>
    <div>
      <Label for="t-desc">Description</Label>
      <Input id="t-desc" bind:value={description} placeholder="What is this for?" class="mt-1" />
    </div>
  </div>
  {#snippet footer()}
    <Button variant="outline" onclick={() => (open = false)}>Cancel</Button>
    <Button onclick={allocate} disabled={allocating}>
      {#if allocating}<Spinner class="size-4" /> Allocating…{:else}<Coins class="size-4" /> Allocate{/if}
    </Button>
  {/snippet}
</Dialog>
