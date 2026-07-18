<script lang="ts" module>
  export type PodState =
    | 'running'
    | 'pending'
    | 'creating'
    | 'stopping'
    | 'stopped'
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
    // Stopped is a resting state, not a dead one — the workspace is intact and
    // the VM can be resumed, so it reads as "info", distinct from Terminated.
    stopped: { variant: 'info', pulse: false, label: 'Stopped' },
    terminated: { variant: 'muted', pulse: false, label: 'Terminated' },
    failed: { variant: 'destructive', pulse: false, label: 'Failed' },
    // Admission-queue states (VmQueueEntry, not PodSession).
    queued: { variant: 'info', pulse: true, label: 'Queued' },
    admitting: { variant: 'info', pulse: true, label: 'Starting' }
  };
</script>

<script lang="ts">
  import { Badge } from '$lib/ui';
  import Spinner from '$lib/icons/Spinner.svelte';

  let { state, class: className }: { state: PodState; class?: string } = $props();

  const cfg = $derived(POD_STATE_CONFIG[state] ?? POD_STATE_CONFIG.terminated);
  // A steady "running" pod gets a live, breathing indicator; transitional
  // states (creating/pending/stopping) spin; terminal states sit still.
  const live = $derived(cfg.variant === 'success' && !cfg.pulse);
</script>

<Badge variant={cfg.variant} class={className}>
  {#if cfg.pulse}
    <Spinner class="size-3" />
  {:else if live}
    <span class="relative flex size-1.5">
      <span class="absolute inline-flex size-full animate-ping-slow rounded-full bg-success"></span>
      <span class="relative inline-flex size-1.5 rounded-full bg-success"></span>
    </span>
  {:else}
    <span
      class="size-1.5 rounded-full"
      class:bg-muted-foreground={cfg.variant === 'muted'}
      class:bg-destructive={cfg.variant === 'destructive'}
    ></span>
  {/if}
  {cfg.label}
</Badge>
