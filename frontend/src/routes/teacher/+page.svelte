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
  type Course = {
    id: string;
    code: string;
    name: string;
    enrolled_count: number;
  };

  let {
    data
  }: {
    data: { balance: number; students: Student[]; courses: Course[]; currentUserId: string };
  } = $props();

  let query = $state('');

  // Scope: '' = every student on the platform (the pre-course behaviour), or a
  // course id, in which case the table is that course's roster.
  let scope = $state('');
  let roster = $state<Student[]>([]);
  let rosterLoading = $state(false);

  const activeCourse = $derived(data.courses.find((c) => c.id === scope) ?? null);
  const scopedStudents = $derived(activeCourse ? roster : data.students);

  async function loadRoster(courseId: string) {
    rosterLoading = true;
    try {
      roster = await api.get<Student[]>(`/courses/${courseId}/roster`);
    } catch (e) {
      toast.error('Could not load the roster', {
        description: e instanceof ApiError ? e.message : ''
      });
      roster = [];
    } finally {
      rosterLoading = false;
    }
  }

  async function onScopeChange() {
    query = '';
    if (scope) {
      await loadRoster(scope);
    } else {
      roster = [];
    }
  }

  async function refreshScope() {
    // After any allocation, refresh whichever list is on screen.
    if (scope) await loadRoster(scope);
    await invalidateAll();
  }

  const filtered = $derived(
    query
      ? scopedStudents.filter(
          (s) =>
            s.email.toLowerCase().includes(query.toLowerCase()) ||
            (s.name ?? '').toLowerCase().includes(query.toLowerCase())
        )
      : scopedStudents
  );

  // Bulk allocation — fund every student on the roster in one all-or-nothing go.
  let bulkOpen = $state(false);
  let bulkAmount = $state(1);
  let bulkDescription = $state('');
  let bulkAllocating = $state(false);

  const bulkTotal = $derived(bulkAmount * roster.length);

  function openBulk() {
    if (!activeCourse) return;
    bulkAmount = 1;
    bulkDescription = `${activeCourse.code} allocation`;
    bulkOpen = true;
  }

  async function allocateToCourse() {
    if (!activeCourse || bulkAllocating) return;
    if (!Number.isFinite(bulkAmount) || bulkAmount <= 0) {
      toast.error('Amount must be a positive number');
      return;
    }
    if (bulkTotal > data.balance) {
      toast.error('Not enough credits', {
        description: `Funding ${roster.length} students at ${bulkAmount} each needs ${bulkTotal.toFixed(2)}; you have ${data.balance.toFixed(2)}.`
      });
      return;
    }
    bulkAllocating = true;
    const id = toast.loading(`Funding ${roster.length} students…`);
    try {
      await api.post(`/courses/${activeCourse.id}/allocate`, {
        amount: bulkAmount,
        description: bulkDescription || 'course_allocation'
      });
      toast.success(`Allocated ${bulkAmount} credits to ${roster.length} students`, {
        id,
        description: activeCourse.code
      });
      bulkOpen = false;
      await refreshScope();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Allocation failed';
      toast.error('Could not allocate to the class', { id, description: msg });
    } finally {
      bulkAllocating = false;
    }
  }

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
      await refreshScope();
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
    <SectionHeader
      title={activeCourse ? `${activeCourse.code} — roster` : 'Students'}
      icon={Users}
      description={activeCourse
        ? activeCourse.name
        : 'Every student on the platform. Pick a course to work with just its roster.'}
    >
      {#snippet action()}
        <div class="flex flex-wrap items-center gap-2">
          <select
            bind:value={scope}
            onchange={onScopeChange}
            aria-label="Course scope"
            class="h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">All students</option>
            {#each data.courses as c (c.id)}
              <option value={c.id}>{c.code} ({c.enrolled_count})</option>
            {/each}
          </select>
          {#if activeCourse}
            <Tooltip content="Allocate credits to every student on this roster">
              <Button
                size="sm"
                onclick={openBulk}
                disabled={data.balance <= 0 || rosterLoading || roster.length === 0}
              >
                <Coins class="size-3.5" /> Allocate to class
              </Button>
            </Tooltip>
          {/if}
          <div class="relative">
            <Search class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input type="search" placeholder="Search students…" bind:value={query} class="h-9 w-40 pl-8 sm:w-64" />
          </div>
        </div>
      {/snippet}
    </SectionHeader>

    {#if data.balance <= 0}
      <div class="rounded-lg border border-warning/30 bg-warning/5 p-3 text-sm text-warning">
        You have no credits yet. An admin needs to grant you a budget before you can allocate to students.
      </div>
    {/if}

    {#if data.courses.length === 0}
      <div class="rounded-lg border border-border bg-muted/20 p-3 text-sm text-muted-foreground">
        You don't own any courses yet. An admin creates courses and assigns them to you — then you
        can manage a roster and fund the whole class at once.
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
          {#if rosterLoading}
            <Table.Row class="hover:bg-transparent">
              <Table.Cell colspan={4} class="py-10 text-center">
                <Spinner class="mx-auto size-5" />
              </Table.Cell>
            </Table.Row>
          {/if}
          {#each rosterLoading ? [] : filtered as s (s.id)}
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
                  <Button
                    variant="outline"
                    size="sm"
                    class="opacity-70 transition-opacity group-hover:opacity-100"
                    onclick={() => openAlloc(s)}
                    disabled={data.balance <= 0}
                  >
                    <Coins class="size-3.5" /> Allocate
                  </Button>
                </Tooltip>
              </Table.Cell>
            </Table.Row>
          {/each}
          {#if !rosterLoading && filtered.length === 0}
            <Table.Row class="hover:bg-transparent">
              <Table.Cell colspan={4} class="py-10 text-center text-sm text-muted-foreground">
                {#if query}
                  No students match your search.
                {:else if activeCourse}
                  No students are enrolled in {activeCourse.code} yet.
                {:else}
                  No students have signed up yet.
                {/if}
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

<Dialog
  bind:open={bulkOpen}
  title="Allocate to the whole class"
  description={activeCourse ? `${activeCourse.code} — ${roster.length} enrolled students` : ''}
>
  <div class="space-y-4">
    <div>
      <Label for="bulk-amount">Credits per student</Label>
      <div class="relative mt-1">
        <Coins class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input id="bulk-amount" type="number" step="0.5" min="0.5" bind:value={bulkAmount} class="pl-8" />
      </div>
    </div>
    <div>
      <Label for="bulk-desc">Description</Label>
      <Input id="bulk-desc" bind:value={bulkDescription} placeholder="What is this for?" class="mt-1" />
    </div>

    <div class="rounded-lg border border-border bg-muted/20 p-3 text-sm">
      <div class="flex items-center justify-between">
        <span class="text-muted-foreground">
          {roster.length} student{roster.length === 1 ? '' : 's'} × {bulkAmount || 0}
        </span>
        <span class="font-semibold tabular-nums">{bulkTotal.toFixed(2)} credits</span>
      </div>
      <div class="mt-1 flex items-center justify-between text-xs text-muted-foreground">
        <span>Your balance after</span>
        <span class="tabular-nums {bulkTotal > data.balance ? 'text-destructive' : ''}">
          {(data.balance - bulkTotal).toFixed(2)}
        </span>
      </div>
    </div>

    {#if bulkTotal > data.balance}
      <p class="text-sm text-destructive">
        Not enough credits — this needs {bulkTotal.toFixed(2)} and you have {data.balance.toFixed(2)}.
        Nobody is funded unless the full amount clears.
      </p>
    {/if}
  </div>

  {#snippet footer()}
    <Button variant="outline" onclick={() => (bulkOpen = false)}>Cancel</Button>
    <Button onclick={allocateToCourse} disabled={bulkAllocating || bulkTotal > data.balance}>
      {#if bulkAllocating}
        <Spinner class="size-4" /> Allocating…
      {:else}
        <Coins class="size-4" /> Allocate {bulkTotal.toFixed(2)}
      {/if}
    </Button>
  {/snippet}
</Dialog>
