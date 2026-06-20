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
    AlertTriangle
  } from 'lucide-svelte';
  import { invalidateAll, goto } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import {
    VM_PLAN_INFO,
    VM_TEMPLATE_INFO,
    type VmPlan,
    type VmTemplate,
    type Pod
  } from '$lib/types';
  import { api, ApiError } from '$lib/api/client';
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
  import PageHeader from '$lib/components/PageHeader.svelte';
  import { confirm } from '$lib/confirm.svelte';
  import { cn, copyToClipboard } from '$lib/utils';

  let { data }: { data: { pods: Pod[]; nodeIp: string; balance: number } } = $props();

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
    let list = data.pods.slice();
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
    active: data.pods.filter((p) =>
      ['running', 'pending', 'creating', 'stopping'].includes(p.state)
    ).length,
    past: data.pods.filter((p) => ['terminated', 'failed'].includes(p.state))
      .length,
    all: data.pods.length
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
      await api.post('/pods/', {
        plan: selectedPlan,
        template: selectedTemplate
      });
      toast.success('VM launched', {
        id,
        description: 'It will be running in a few seconds.'
      });
      await invalidateAll();
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
      await invalidateAll();
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
  <PageHeader
    title="Virtual Machines"
    description="Launch new VMs and manage your existing instances."
  />

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
                'group relative rounded-xl border p-4 text-left transition-all',
                'hover:border-primary/50 hover:shadow-sm',
                selectedPlan === plan
                  ? 'border-primary bg-primary/5 ring-2 ring-primary/30'
                  : 'border-border bg-card'
              )}
              onclick={() => (selectedPlan = plan as VmPlan)}
            >
              <div class="flex items-start justify-between">
                <div>
                  <div class="text-base font-semibold capitalize">{plan}</div>
                  <div class="mt-0.5 text-xs text-muted-foreground">
                    {info.description}
                  </div>
                </div>
                <div
                  class={cn(
                    'flex size-5 items-center justify-center rounded-full border transition-colors',
                    selectedPlan === plan
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border bg-card'
                  )}
                >
                  {#if selectedPlan === plan}<Check class="size-3" />{/if}
                </div>
              </div>
              <div class="mt-4 grid grid-cols-3 gap-2 text-xs">
                <div class="rounded-md bg-muted/50 p-2">
                  <div class="flex items-center gap-1 text-muted-foreground">
                    <Cpu class="size-3 text-primary" /> CPU
                  </div>
                  <div class="mt-0.5 font-mono font-semibold">{info.cpu}</div>
                </div>
                <div class="rounded-md bg-muted/50 p-2">
                  <div class="flex items-center gap-1 text-muted-foreground">
                    <MemoryStick class="size-3 text-info" /> RAM
                  </div>
                  <div class="mt-0.5 font-mono font-semibold">{info.memory}</div>
                </div>
                <div class="rounded-md bg-muted/50 p-2">
                  <div class="flex items-center gap-1 text-muted-foreground">
                    <HardDrive class="size-3 text-success" /> Disk
                  </div>
                  <div class="mt-0.5 font-mono font-semibold">{info.disk}</div>
                </div>
              </div>
              <div class="mt-3 flex items-center gap-1.5 text-sm font-semibold text-primary">
                <Coins class="size-3.5" /> {info.rate} credit{info.rate === 1 ? '' : 's'}/hr
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
              class={cn(
                'group rounded-xl border p-4 text-left transition-all hover:border-primary/50 hover:shadow-sm',
                selectedTemplate === key
                  ? 'border-primary bg-primary/5 ring-2 ring-primary/30'
                  : 'border-border bg-card'
              )}
              onclick={() => (selectedTemplate = key as VmTemplate)}
            >
              <div class="flex items-center gap-2">
                <div
                  class={cn(
                    'flex size-8 items-center justify-center rounded-md text-sm font-bold uppercase transition-transform group-hover:scale-110',
                    templateAccent[info.accent] ?? 'bg-muted text-foreground'
                  )}
                >
                  {info.name.slice(0, 1)}
                </div>
                <div class="font-semibold">{info.name}</div>
                {#if selectedTemplate === key}
                  <Check class="ml-auto size-4 text-primary" />
                {/if}
              </div>
              <p class="mt-2 text-xs text-muted-foreground">{info.tagline}</p>
              <p class="mt-1 text-[11px] text-muted-foreground/80">
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
