<script lang="ts">
  import {
    ListOrdered,
    ArrowLeft,
    XCircle,
    Cpu,
    MemoryStick,
    Info,
    Server
  } from 'lucide-svelte';
  import { onMount, untrack } from 'svelte';
  import { invalidateAll, goto } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import {
    VM_PLAN_INFO,
    VM_TEMPLATE_INFO,
    type VmPlan,
    type VmTemplate,
    type QueueEntry
  } from '$lib/types';
  import { api, ApiError } from '$lib/api/client';
  import { Button, Card, CardContent, Badge } from '$lib/ui';
  import PageTitle from '$lib/components/PageTitle.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { confirm } from '$lib/confirm.svelte';
  import { relTime } from '$lib/utils';

  let { data }: { data: { entries: QueueEntry[] } } = $props();

  // Render from local state seeded once by SSR (untrack keeps this to the
  // initial value), then poll so positions advance as capacity frees and other
  // users' requests are admitted ahead of / behind us.
  let entries = $state<QueueEntry[]>(untrack(() => data.entries));
  let cancelling = $state<string | null>(null);

  async function refresh() {
    try {
      entries = await api.get<QueueEntry[]>('/pods/queue');
    } catch {
      // Transient failure — keep the last known list rather than blanking it.
    }
  }

  onMount(() => {
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  });

  function planLabel(plan: string): string {
    return plan.charAt(0).toUpperCase() + plan.slice(1);
  }

  function templateLabel(template: string): string {
    return VM_TEMPLATE_INFO[template as VmTemplate]?.name ?? template;
  }

  async function cancelEntry(entry: QueueEntry) {
    // Only a still-'queued' request can be pulled; once 'admitting' the
    // orchestrator create is already in flight and the API returns 409.
    if (entry.state !== 'queued') return;

    const ok = await confirm({
      title: 'Cancel this request?',
      description:
        'It will be removed from the queue and no VM will be created. You can request a new one at any time.',
      confirmLabel: 'Cancel request',
      variant: 'destructive'
    });
    if (!ok) return;

    cancelling = entry.id;
    const id = toast.loading('Cancelling request…');
    try {
      await api.delete(`/pods/queue/${entry.id}`);
      toast.success('Request cancelled', { id });
      await Promise.all([refresh(), invalidateAll()]);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Failed to cancel request';
      toast.error('Cancel failed', { id, description: msg });
    } finally {
      cancelling = null;
    }
  }
</script>

<div class="space-y-6">
  <PageTitle
    title="Queue"
    eyebrow="Virtual Machines"
    eyebrowIcon={ListOrdered}
    description="VM requests waiting for cluster capacity. Each one starts automatically, in order, as running VMs free up resources."
  >
    {#snippet leading()}
      <button
        type="button"
        onclick={() => goto('/pods')}
        aria-label="Back to Virtual Machines"
        class="flex size-9 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <ArrowLeft class="size-4" />
      </button>
    {/snippet}
    {#snippet badge()}
      <Badge variant="muted">{entries.length} waiting</Badge>
    {/snippet}
  </PageTitle>

  {#if entries.length === 0}
    <Card class="border-dashed bg-muted/20">
      <CardContent class="flex flex-col items-center gap-3 py-14 text-center">
        <span
          class="flex size-11 items-center justify-center rounded-xl bg-muted text-muted-foreground"
        >
          <ListOrdered class="size-5" />
        </span>
        <div class="space-y-1">
          <p class="text-sm font-medium text-foreground">Your queue is empty</p>
          <p class="text-sm text-muted-foreground">
            When the cluster is full, new VM requests wait here until capacity
            frees up.
          </p>
        </div>
        <Button variant="outline" onclick={() => goto('/pods')}>
          Launch a VM
        </Button>
      </CardContent>
    </Card>
  {:else}
    <div
      class="flex items-start gap-2.5 rounded-lg border border-info/30 bg-info/[0.06] px-4 py-3 text-sm text-muted-foreground"
    >
      <Info class="mt-0.5 size-4 shrink-0 text-info" />
      <p>
        Requests are admitted first-come, first-served. A request already
        <span class="font-medium text-foreground">starting</span> can no longer
        be cancelled.
      </p>
    </div>

    <div class="space-y-3">
      {#each entries as entry (entry.id)}
        {@const starting = entry.state !== 'queued'}
        {@const info = VM_PLAN_INFO[entry.plan as VmPlan]}
        <Card
          class={`flex items-center gap-4 p-4 transition-colors sm:gap-5 ${starting ? 'border-primary/50 ring-1 ring-primary/15' : ''}`}
        >
          <!-- Position ring -->
          <span
            class={`grid size-11 shrink-0 place-items-center rounded-full font-mono text-sm font-bold tabular-nums ${
              starting ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
            }`}
          >
            {entry.position}
          </span>

          <!-- VM info -->
          <div class="flex min-w-0 flex-1 items-center gap-3">
            <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-muted text-foreground">
              <Server class="size-4" />
            </span>
            <div class="min-w-0">
              <div class="text-sm font-semibold">{planLabel(entry.plan)}</div>
              <div class="mt-0.5 flex items-center gap-3 text-[11px] text-muted-foreground">
                <span class="truncate">{templateLabel(entry.template)}</span>
                {#if info}
                  <span class="inline-flex items-center gap-1"><Cpu class="size-3" /> {info.cpu}</span>
                  <span class="inline-flex items-center gap-1"><MemoryStick class="size-3" /> {info.memory}</span>
                {/if}
              </div>
            </div>
          </div>

          <!-- Status + progress / wait -->
          <div class="hidden w-48 shrink-0 flex-col items-end gap-2 sm:flex">
            <StatusBadge state={entry.state} />
            {#if starting}
              <div class="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div class="h-full w-2/3 animate-pulse rounded-full bg-primary"></div>
              </div>
            {:else}
              <span class="whitespace-nowrap text-xs text-muted-foreground">
                Requested {relTime(new Date(entry.created_at))}
              </span>
            {/if}
          </div>

          <!-- Cancel -->
          <Button
            variant="ghost"
            size="sm"
            class="shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={entry.state !== 'queued' || cancelling === entry.id}
            onclick={() => cancelEntry(entry)}
          >
            <XCircle class="size-4" />
            <span class="hidden sm:inline">Cancel</span>
          </Button>
        </Card>
      {/each}
    </div>
  {/if}
</div>
