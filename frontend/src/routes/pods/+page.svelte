<script lang="ts">
  import {
    Plus,
    Server,
    Check,
    Cpu,
    MemoryStick,
    HardDrive,
    Coins,
    Search,
    MoreVertical,
    Square,
    ExternalLink,
    Terminal,
    Code2,
    Filter,
    AlertTriangle,
    ListOrdered,
    Gauge
  } from 'lucide-svelte';
  import { onMount, untrack } from 'svelte';
  import { invalidateAll, goto } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import {
    VM_PLAN_INFO,
    VM_TEMPLATE_INFO,
    type VmPlan,
    type VmTemplate,
    type Pod,
    type Availability,
    type CreatePodResult
  } from '$lib/types';
  import { capacityTone, fmtCapacity } from '$lib/capacity/format';
  import { api, ApiError } from '$lib/api/client';
  import StatCard from '$lib/components/StatCard.svelte';
  import {
    Button,
    Card,
    CardHeader,
    CardTitle,
    CardDescription,
    CardContent,
    Input,
    Badge,
    Separator,
    Tabs,
    Pagination,
    DropdownMenu,
    Dialog
  } from '$lib/ui';
  import PodCard from '$lib/components/PodCard.svelte';
  import PageTitle from '$lib/components/PageTitle.svelte';
  import { confirm } from '$lib/confirm.svelte';
  import { cn, copyToClipboard } from '$lib/utils';

  let {
    data
  }: {
    data: {
      pods: Pod[];
      nodeIp: string;
      balance: number;
      availability: Availability | null;
    };
  } = $props();
  let livePods = $state<Pod[]>(data.pods);

  // Live cluster availability readout. Seeded once from SSR (untrack keeps this
  // to the initial value), then polled so the free-capacity and queue-length
  // figures stay fresh while the page is open.
  let availability = $state<Availability | null>(untrack(() => data.availability));

  async function refreshPods() {
    try {
      livePods = await api.get<Pod[]>('/pods/');
    } catch {
      // Keep the last known state on transient failures.
    }
  }

  async function refreshAvailability() {
    try {
      availability = await api.get<Availability>('/pods/availability');
    } catch {
      // Keep the last known value on a transient failure — the endpoint is
      // best-effort and must never disrupt the page.
    }
  }

  onMount(() => {
    const availabilityTimer = setInterval(refreshAvailability, 5000);
    const podsTimer = setInterval(refreshPods, 5000);
    return () => {
      clearInterval(availabilityTimer);
      clearInterval(podsTimer);
    };
  });

  const cpuTone = $derived(
    capacityTone(availability?.cpu.free_cores, availability?.cpu.total_cores)
  );
  const memTone = $derived(
    capacityTone(availability?.memory.free_gib, availability?.memory.total_gib)
  );
  const storageTone = $derived(
    capacityTone(availability?.storage.free_gib, availability?.storage.total_gib)
  );
  const queueLength = $derived(availability?.queue_length ?? 0);

  // Modest, vibrant per-image accent — visual only, used on the small icon tile.
  // Kept as static class strings so Tailwind's JIT can detect them.
  const templateAccent: Record<string, string> = {
    orange: 'bg-orange-500/15 text-orange-600 dark:text-orange-400',
    yellow: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
    blue: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
    red: 'bg-rose-500/15 text-rose-600 dark:text-rose-400'
  };

  let selectedPlan = $state<VmPlan>('small');
  let selectedTemplate = $state<VmTemplate>('ubuntu');
  let creating = $state(false);

  // List filters
  let query = $state('');
  let stateFilter = $state<'all' | 'active' | 'past'>('active');

  const PER_PAGE = 12;
  let page = $state(1);

  // Reset to the first page whenever the filtered set changes.
  $effect(() => {
    query;
    stateFilter;
    page = 1;
  });

  let sshDialogOpen = $state(false);
  let sshDialogPod = $state<Pod | null>(null);

  const planRate = $derived(VM_PLAN_INFO[selectedPlan].rate);
  const canAfford = $derived(data.balance >= planRate);

  const filteredPods = $derived.by(() => {
    let list = livePods.slice();
    if (stateFilter === 'active') {
      list = list.filter((p) =>
        ['running', 'pending', 'creating', 'stopping'].includes(p.state)
      );
    } else if (stateFilter === 'past') {
      list = list.filter((p) =>
        ['terminated', 'failed'].includes(p.state)
      );
    }
    const q = query.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (p) =>
          p.id.toLowerCase().includes(q) ||
          p.image.toLowerCase().includes(q) ||
          p.plan.toLowerCase().includes(q)
      );
    }
    return list;
  });

  const pagedPods = $derived(
    filteredPods.slice((page - 1) * PER_PAGE, page * PER_PAGE)
  );

  const counts = $derived({
    active: livePods.filter((p) =>
      ['running', 'pending', 'creating', 'stopping'].includes(p.state)
    ).length,
    past: livePods.filter((p) => ['terminated', 'failed'].includes(p.state))
      .length,
    all: livePods.length
  });

  async function createPod() {
    if (creating) return;
    if (!canAfford) {
      toast.error(
        `You need at least ${planRate} credit${planRate === 1 ? '' : 's'} to launch this VM`,
        {
          description: `Current balance: ${data.balance.toFixed(2)} credits.`
        }
      );
      return;
    }

    const ok = await confirm({
      title: 'Launch new VM?',
      description: `Plan: ${selectedPlan} (${VM_PLAN_INFO[selectedPlan].cpu}, ${VM_PLAN_INFO[selectedPlan].memory}). Billing starts at ${planRate} credit/hour.`,
      confirmLabel: 'Launch',
      variant: 'default'
    });
    if (!ok) return;

    creating = true;
    const id = toast.loading(`Launching ${selectedPlan} VM…`);
    try {
      const res = await api.post<CreatePodResult>('/pods/', {
        plan: selectedPlan,
        template: selectedTemplate
      });
      // The cluster was full: the request was enqueued (HTTP 202) rather than
      // started. The API client hides the status code, so we branch on the
      // `queued` discriminator in the body.
      if ('queued' in res && res.queued) {
        toast.info(`Cluster is full — you're queued at position ${res.position}`, {
          id,
          description: 'Your VM starts automatically as capacity frees up.'
        });
        await goto('/pods/queue');
        return;
      }
      toast.success('VM launched', {
        id,
        description: 'It will be running in a few seconds.'
      });
      await Promise.all([invalidateAll(), refreshAvailability(), refreshPods()]);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Failed to launch VM';
      toast.error('Launch failed', { id, description: msg });
    } finally {
      creating = false;
    }
  }

  async function terminatePod(pod: Pod) {
    const ok = await confirm({
      title: `Terminate VM ${pod.id.slice(0, 8)}?`,
      description:
        'This will permanently stop the container, drop unsaved changes, and stop billing. This cannot be undone.',
      confirmLabel: 'Terminate',
      variant: 'destructive'
    });
    if (!ok) return;

    const id = toast.loading('Terminating VM…');
    try {
      await api.delete(`/pods/${pod.id}`);
      toast.success('VM terminated', { id });
      await Promise.all([invalidateAll(), refreshAvailability(), refreshPods()]);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Failed to terminate VM';
      toast.error('Termination failed', { id, description: msg });
    }
  }

  function openSshInfo(pod: Pod) {
    sshDialogPod = pod;
    sshDialogOpen = true;
  }

  async function copySsh(pod: Pod) {
    if (!pod.ssh_port) return;
    try {
      await copyToClipboard(`ssh root@${data.nodeIp} -p ${pod.ssh_port}`);
      toast.success('SSH command copied');
    } catch {
      toast.error('Could not access clipboard');
    }
  }

  function vscodeUrl(pod: Pod): string {
    return `/${pod.user_id}/code/${pod.id}/`;
  }
</script>

<div class="space-y-6">
  <!-- Header -->
  <PageTitle
    title="Virtual Machines"
    description="Launch new VMs and manage your existing instances."
  />

  <!-- Cluster availability: free vs total capacity + queue depth. Polls every
       5s and degrades to em dashes when the orchestrator can't be reached. -->
  <section class="animate-fade-up" aria-label="Cluster availability">
    <div class="mb-3 flex items-center justify-between gap-3">
      <h2 class="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
        <Gauge class="size-4" />
        Cluster availability
      </h2>
      {#if availability?.nodes_ready != null}
        <span class="text-xs text-muted-foreground">
          {availability.nodes_ready} node{availability.nodes_ready === 1 ? '' : 's'} ready
        </span>
      {/if}
    </div>
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        compact
        label="Free CPU"
        value="{fmtCapacity(availability?.cpu.free_cores)} / {fmtCapacity(availability?.cpu.total_cores)}"
        sub="cores left to reserve"
        icon={Cpu}
        tone={cpuTone}
      />
      <StatCard
        compact
        label="Free memory"
        value="{fmtCapacity(availability?.memory.free_gib)} / {fmtCapacity(availability?.memory.total_gib)}"
        sub="GiB available"
        icon={MemoryStick}
        tone={memTone}
      />
      <StatCard
        compact
        label="Free storage"
        value="{fmtCapacity(availability?.storage.free_gib)} / {fmtCapacity(availability?.storage.total_gib)}"
        sub="GiB workspace quota"
        icon={HardDrive}
        tone={storageTone}
      />
      <StatCard
        compact
        label="In queue"
        value={queueLength}
        sub={queueLength > 0 ? 'waiting for capacity' : 'no waiting requests'}
        icon={ListOrdered}
        tone={queueLength > 0 ? 'warning' : 'default'}
        href="/pods/queue"
      />
    </div>
    <!-- Without this the CPU figure looks broken: a "1 CPU" VM only moves it by
         0.25, because CPU is reserved at a quarter of the plan limit while
         memory and storage are reserved in full. Only worth saying once there
         are real figures to explain — the cards are all em dashes until then. -->
    {#if availability}
      <p class="mt-3 text-xs leading-relaxed text-muted-foreground">
        A VM reserves a <strong class="font-medium text-foreground">quarter</strong> of its plan's
        CPU and bursts up to the full limit whenever cores are idle — so a 1 CPU VM takes 0.25 from
        free CPU. Memory and storage are reserved in full. Free storage is a workspace quota, not
        measured disk.
      </p>
    {/if}
  </section>

  <!-- Launch panel -->
  <Card class="animate-fade-up surface-glow overflow-hidden">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <span
          class="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-info text-primary-foreground shadow-sm"
        >
          <Plus class="size-4" />
        </span>
        Launch a new VM
      </CardTitle>
      <CardDescription>
        Pick a resource plan and a base image. Billing is per minute, charged
        at the plan's hourly rate.
      </CardDescription>
    </CardHeader>
    <Separator />
    <CardContent class="space-y-6 pt-6">
      <!-- Plan picker -->
      <div>
        <h3 class="mb-3 text-sm font-semibold">1. Resource plan</h3>
        <div class="grid gap-3 sm:grid-cols-3">
          {#each Object.entries(VM_PLAN_INFO) as [plan, info] (plan)}
            <button
              type="button"
              class={cn(
                'group relative flex flex-col rounded-xl border p-3.5 text-left transition-all',
                'hover:border-primary/50 hover:shadow-sm',
                selectedPlan === plan
                  ? 'border-primary bg-primary/[0.04] ring-2 ring-primary/25'
                  : 'border-border bg-card'
              )}
              onclick={() => (selectedPlan = plan as VmPlan)}
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="text-sm font-semibold capitalize">{plan}</div>
                  <p class="mt-0.5 text-xs leading-snug text-muted-foreground">
                    {info.description}
                  </p>
                </div>
                <div
                  class={cn(
                    'flex size-5 shrink-0 items-center justify-center rounded-full border transition-colors',
                    selectedPlan === plan
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border bg-card group-hover:border-primary/40'
                  )}
                >
                  {#if selectedPlan === plan}<Check class="size-3" />{/if}
                </div>
              </div>

              <div
                class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs font-medium"
              >
                <span class="inline-flex items-center gap-1.5">
                  <Cpu class="size-3.5 text-primary" />
                  {info.cpu}
                </span>
                <span class="inline-flex items-center gap-1.5">
                  <MemoryStick class="size-3.5 text-info" />
                  {info.memory}
                </span>
                <span class="inline-flex items-center gap-1.5">
                  <HardDrive class="size-3.5 text-success" />
                  {info.disk}
                </span>
              </div>

              <div
                class="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-primary"
              >
                <Coins class="size-3.5" />
                {info.rate} credit{info.rate === 1 ? '' : 's'}<span
                  class="font-normal text-muted-foreground">/hr</span
                >
              </div>
            </button>
          {/each}
        </div>
      </div>

      <!-- Template picker -->
      <div>
        <h3 class="mb-3 text-sm font-semibold">2. Base image</h3>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {#each Object.entries(VM_TEMPLATE_INFO) as [key, info] (key)}
            <button
              type="button"
              aria-label={info.name}
              class={cn(
                'group relative flex flex-col rounded-xl border p-3.5 text-left transition-all hover:border-primary/50 hover:shadow-sm',
                selectedTemplate === key
                  ? 'border-primary bg-primary/[0.04] ring-2 ring-primary/25'
                  : 'border-border bg-card'
              )}
              onclick={() => (selectedTemplate = key as VmTemplate)}
            >
              {#if selectedTemplate === key}
                <div
                  class="absolute right-2.5 top-2.5 flex size-5 items-center justify-center rounded-full bg-primary text-primary-foreground"
                >
                  <Check class="size-3" />
                </div>
              {/if}
              <div class="flex items-center gap-2.5">
                <div
                  class={cn(
                    'flex size-9 shrink-0 items-center justify-center rounded-lg text-base font-bold uppercase transition-transform group-hover:scale-105',
                    templateAccent[info.accent] ?? 'bg-muted text-foreground'
                  )}
                >
                  {info.name.slice(0, 1)}
                </div>
                <div class="min-w-0 pr-5">
                  <div class="truncate text-sm font-semibold">{info.name}</div>
                  <p class="truncate text-[11px] text-muted-foreground">
                    {info.tagline}
                  </p>
                </div>
              </div>
              <p class="mt-2.5 text-[11px] leading-snug text-muted-foreground">
                {info.description}
              </p>
            </button>
          {/each}
        </div>
      </div>

      <Separator />

      <!-- Cost summary + launch -->
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div class="text-sm">
          <div class="text-muted-foreground">Estimated cost</div>
          <div class="text-2xl font-bold tracking-tight">
            {planRate} credit{planRate === 1 ? '' : 's'}
            <span class="text-base font-medium text-muted-foreground">/ hour</span>
          </div>
          <div class="text-xs text-muted-foreground">
            Your balance: {data.balance.toFixed(2)} credits
          </div>
        </div>
        <div class="flex flex-col items-end gap-2">
          {#if !canAfford}
            <div
              class="inline-flex items-center gap-1.5 rounded-md bg-destructive/10 px-2.5 py-1 text-xs font-medium text-destructive"
            >
              <AlertTriangle class="size-3.5" />
              Insufficient credits — need {planRate}.
            </div>
          {/if}
          <Button
            onclick={createPod}
            disabled={creating || !canAfford}
            size="lg"
          >
            <Plus class="size-4" />
            {creating ? 'Launching…' : 'Launch VM'}
          </Button>
        </div>
      </div>
    </CardContent>
  </Card>

  <!-- Pods list -->
  <section class="animate-fade-up" style="animation-delay: 60ms">
    <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-center gap-2">
        <h2 class="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <span
            class="flex size-6 items-center justify-center rounded-md bg-primary/10 text-primary"
          >
            <Server class="size-3.5" />
          </span>
          Your VMs
        </h2>
        <Badge variant="muted">{counts.all} total</Badge>
      </div>
      <div class="flex items-center gap-2">
        <div class="relative">
          <Search
            class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            placeholder="Search ID, image, plan…"
            bind:value={query}
            class="h-9 w-56 pl-8"
          />
        </div>
      </div>
    </div>

    <Tabs.Root bind:value={stateFilter}>
      <Tabs.List>
        <Tabs.Trigger value="active">
          Active <Badge variant="muted">{counts.active}</Badge>
        </Tabs.Trigger>
        <Tabs.Trigger value="past">
          History <Badge variant="muted">{counts.past}</Badge>
        </Tabs.Trigger>
        <Tabs.Trigger value="all">All</Tabs.Trigger>
      </Tabs.List>

      <Tabs.Content value="active">
        {@render podGrid()}
      </Tabs.Content>
      <Tabs.Content value="past">
        {@render podGrid()}
      </Tabs.Content>
      <Tabs.Content value="all">
        {@render podGrid()}
      </Tabs.Content>
    </Tabs.Root>
  </section>
</div>

{#snippet podGrid()}
  {#if filteredPods.length === 0}
    <Card class="border-dashed bg-muted/20">
      <CardContent class="py-12 text-center text-sm text-muted-foreground">
        {#if query}
          No VMs match "<span class="font-medium text-foreground">{query}</span>".
        {:else if stateFilter === 'active'}
          No active VMs. Launch one above to get started.
        {:else if stateFilter === 'past'}
          You haven't terminated any VMs yet.
        {:else}
          You haven't created any VMs yet.
        {/if}
      </CardContent>
    </Card>
  {:else}
    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {#each pagedPods as pod, i (pod.id)}
        <div
          class="animate-fade-up"
          style="animation-delay: {Math.min(i * 40, 320)}ms"
        >
          <PodCard {pod} href="/pods/{pod.id}">
            {#snippet actions()}
              <DropdownMenu.Root>
                <DropdownMenu.Trigger>
                  {#snippet child({ props })}
                    <button
                      {...props}
                      onclick={(e) => e.preventDefault()}
                      class="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      aria-label="More actions"
                    >
                      <MoreVertical class="size-4" />
                    </button>
                  {/snippet}
                </DropdownMenu.Trigger>
                <DropdownMenu.Content>
                  <DropdownMenu.Item onclick={() => goto(`/pods/${pod.id}`)}>
                    <ExternalLink class="size-4" /> Open
                  </DropdownMenu.Item>
                  {#if pod.state === 'running' && pod.ssh_port}
                    <DropdownMenu.Item onclick={() => copySsh(pod)}>
                      <Terminal class="size-4" /> Copy SSH command
                    </DropdownMenu.Item>
                    <DropdownMenu.Item onclick={() => openSshInfo(pod)}>
                      <Terminal class="size-4" /> Show SSH info
                    </DropdownMenu.Item>
                    {#if pod.vscode_port}
                      <DropdownMenu.Item
                        onclick={() => window.open(vscodeUrl(pod), '_blank')}
                      >
                        <Code2 class="size-4" /> Open VS Code
                      </DropdownMenu.Item>
                    {/if}
                    <DropdownMenu.Separator />
                  {/if}
                  {#if !['terminated', 'failed'].includes(pod.state)}
                    <DropdownMenu.Item danger onclick={() => terminatePod(pod)}>
                      <Square class="size-4" /> Terminate
                    </DropdownMenu.Item>
                  {/if}
                </DropdownMenu.Content>
              </DropdownMenu.Root>
            {/snippet}
          </PodCard>
        </div>
      {/each}
    </div>
    {#if filteredPods.length > PER_PAGE}
      <Pagination
        class="mt-6"
        count={filteredPods.length}
        perPage={PER_PAGE}
        bind:page
        itemLabel="VM"
      />
    {/if}
  {/if}
{/snippet}

<!-- SSH info dialog -->
<Dialog
  bind:open={sshDialogOpen}
  title="SSH access"
  description={sshDialogPod ? `VM ${sshDialogPod.id.slice(0, 8)}` : ''}
>
  {#if sshDialogPod && sshDialogPod.ssh_port}
    <div class="space-y-3 text-sm">
      <div>
        <div class="mb-1 text-xs font-medium text-muted-foreground">Connect command</div>
        <code
          class="block w-full select-all rounded-md border border-border bg-muted/50 px-3 py-2 font-mono text-xs"
        >
          ssh root@{data.nodeIp} -p {sshDialogPod.ssh_port}
        </code>
      </div>
      {#if sshDialogPod.ssh_password}
        <div>
          <div class="mb-1 text-xs font-medium text-muted-foreground">Root password</div>
          <code
            class="block w-full select-all rounded-md border border-border bg-muted/50 px-3 py-2 font-mono text-xs"
          >
            {sshDialogPod.ssh_password}
          </code>
        </div>
      {/if}
      <p class="text-xs text-muted-foreground">
        For passwordless access, add an SSH key in
        <a href="/settings/ssh-keys" class="font-medium text-primary hover:underline">
          Settings → SSH Keys
        </a>.
      </p>
    </div>
  {/if}
  {#snippet footer()}
    <Button
      variant="outline"
      onclick={() => sshDialogPod && copySsh(sshDialogPod)}
    >
      Copy command
    </Button>
    <Button onclick={() => (sshDialogOpen = false)}>Done</Button>
  {/snippet}
</Dialog>
