<script lang="ts">
  import {
    Server,
    Cpu,
    MemoryStick,
    Terminal,
    ArrowUpRight,
    Container
  } from 'lucide-svelte';
  import type { Snippet } from 'svelte';
  import type { Pod } from '$lib/types';
  import { Card } from '$lib/ui';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { relTime, shortId } from '$lib/utils';

  let {
    pod,
    href,
    actions
  }: { pod: Pod; href?: string; actions?: Snippet } = $props();

  const imageName = $derived(pod.image?.split('/').pop()?.split(':')[0] ?? pod.image);
  const isRunning = $derived(pod.state === 'running');
</script>

{#snippet body()}
  <!-- Header -->
  <div class="flex items-start justify-between gap-2">
    <div class="flex min-w-0 items-center gap-2.5">
      <div
        class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary/15 to-info/15 text-primary ring-1 ring-inset ring-primary/10"
      >
        <Server class="size-4" />
      </div>
      <div class="min-w-0">
        <div class="truncate font-mono text-sm font-semibold leading-tight">
          {shortId(pod.id, 8)}
        </div>
        <div class="text-xs capitalize text-muted-foreground">{pod.plan}</div>
      </div>
    </div>
    <div class="flex shrink-0 items-center gap-1">
      <StatusBadge state={pod.state} />
      {#if actions}
        {@render actions()}
      {/if}
    </div>
  </div>

  <!-- Specs — compact chips instead of a tall spec list -->
  <div class="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11px] font-medium">
    <span
      class="inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-md bg-muted/50 px-2 py-1"
      title={pod.image}
    >
      <Container class="size-3.5 shrink-0 text-muted-foreground" />
      <span class="truncate">{imageName}</span>
    </span>
    <span class="inline-flex items-center gap-1.5 rounded-md bg-muted/50 px-2 py-1">
      <Cpu class="size-3.5 text-primary" />
      {pod.cpu ?? '—'} vCPU
    </span>
    <span class="inline-flex items-center gap-1.5 rounded-md bg-muted/50 px-2 py-1">
      <MemoryStick class="size-3.5 text-info" />
      {pod.memory ?? '—'}
    </span>
  </div>

  {#if isRunning && pod.ssh_port}
    <div class="mt-1.5 text-[11px] font-medium">
      <span
        class="inline-flex items-center gap-1.5 rounded-md bg-primary/10 px-2 py-1 font-mono text-primary"
      >
        <Terminal class="size-3.5" />
        :{pod.ssh_port}
      </span>
    </div>
  {/if}

  <!-- Footer -->
  <div
    class="mt-3.5 flex items-center justify-between border-t border-border/70 pt-2.5 text-xs text-muted-foreground"
  >
    <span>Created {relTime(pod.created_at)}</span>
    {#if href}
      <span
        class="inline-flex items-center gap-1 rounded-md px-2 py-1 font-medium text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground"
      >
        {isRunning ? 'Connect' : 'Open'}
        <ArrowUpRight class="size-3" />
      </span>
    {/if}
  </div>
{/snippet}

{#if href}
  <a {href} class="group block h-full">
    <Card class="card-lift h-full p-4 hover:border-primary/40 hover:shadow-md">
      {@render body()}
    </Card>
  </a>
{:else}
  <Card class="h-full p-4">
    {@render body()}
  </Card>
{/if}
