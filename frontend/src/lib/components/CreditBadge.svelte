<script lang="ts">
  import { Coins } from 'lucide-svelte';
  import { cn } from '$lib/utils';

  let {
    balance = 0,
    class: className
  }: { balance: number; class?: string } = $props();

  const tone = $derived(
    balance > 50
      ? 'bg-success/10 text-success border-success/30'
      : balance > 10
        ? 'bg-warning/10 text-warning border-warning/30'
        : 'bg-destructive/10 text-destructive border-destructive/30'
  );
</script>

<a
  href="/credits"
  class={cn(
    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-sm font-medium transition-colors hover:opacity-90',
    tone,
    className
  )}
>
  <Coins class="size-3.5" />
  <span>{balance.toFixed(1)}</span>
  <span class="opacity-70">credits</span>
</a>
