<script lang="ts" module>
  export type PodState =
    | 'running'
    | 'pending'
    | 'creating'
    | 'stopping'
    | 'terminated'
    | 'failed'
    | string;

  type Cfg = {
    variant: 'success' | 'warning' | 'info' | 'destructive' | 'muted';
    pulse: boolean;
    label: string;
  };

  export const POD_STATE_CONFIG: Record<string, Cfg> = {
    running: { variant: 'success', pulse: false, label: 'Running' },
    pending: { variant: 'warning', pulse: true, label: 'Pending' },
    creating: { variant: 'info', pulse: true, label: 'Creating' },
    stopping: { variant: 'warning', pulse: true, label: 'Stopping' },
    terminated: { variant: 'muted', pulse: false, label: 'Terminated' },
    failed: { variant: 'destructive', pulse: false, label: 'Failed' }
  };
</script>

<script lang="ts">
  import { Loader2 } from 'lucide-svelte';
  import { Badge } from '$lib/ui';

  let { state, class: className }: { state: PodState; class?: string } = $props();

  const cfg = $derived(POD_STATE_CONFIG[state] ?? POD_STATE_CONFIG.terminated);
</script>

<Badge variant={cfg.variant} class={className}>
  {#if cfg.pulse}
    <Loader2 class="size-3 animate-spin" />
  {:else}
    <span
      class="size-1.5 rounded-full"
      class:bg-success={cfg.variant === 'success'}
      class:bg-muted-foreground={cfg.variant === 'muted'}
      class:bg-destructive={cfg.variant === 'destructive'}
    ></span>
  {/if}
  {cfg.label}
</Badge>
