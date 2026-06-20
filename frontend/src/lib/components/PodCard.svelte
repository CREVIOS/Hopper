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
</script>

{#snippet body()}
  <div class="flex items-start justify-between gap-2">
    <div class="flex items-center gap-2.5 min-w-0">
      <div
        class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary/15 to-info/15 text-primary"
      >
        <Server class="size-4" />
      </div>
      <div class="min-w-0">
        <div class="font-mono text-sm font-semibold truncate">
          {shortId(pod.id, 8)}
        </div>
        <div class="text-xs text-muted-foreground capitalize">{pod.plan}</div>
      </div>
    </div>
    <div class="flex shrink-0 items-center gap-1">
      <StatusBadge state={pod.state} />
      {#if actions}
        {@render actions()}
      {/if}
    </div>
  </div>

  <dl class="mt-4 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
    <div class="flex items-center gap-1.5 text-muted-foreground">
      <Container class="size-3.5" /> Image
    </div>
    <dd class="text-right font-medium truncate" title={pod.image}>{imageName}</dd>

    <div class="flex items-center gap-1.5 text-muted-foreground">
      <Cpu class="size-3.5" /> vCPU
    </div>
    <dd class="text-right font-medium">{pod.cpu ?? '—'}</dd>

    <div class="flex items-center gap-1.5 text-muted-foreground">
      <MemoryStick class="size-3.5" /> Memory
    </div>
    <dd class="text-right font-medium">{pod.memory ?? '—'}</dd>

    {#if pod.ssh_port && pod.state === 'running'}
      <div class="flex items-center gap-1.5 text-muted-foreground">
        <Terminal class="size-3.5" /> SSH
      </div>
      <dd class="text-right font-mono text-primary">:{pod.ssh_port}</dd>
    {/if}
  </dl>

  <div
    class="mt-4 flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground"
  >
    <span>Created {relTime(pod.created_at)}</span>
    {#if href}
      <span class="inline-flex items-center gap-1 text-foreground opacity-0 transition-opacity group-hover:opacity-100">
        Open <ArrowUpRight class="size-3" />
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
