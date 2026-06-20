<script lang="ts">
  import { Tabs as Bits } from 'bits-ui';
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    children,
    class: className
  }: { children: Snippet; class?: string } = $props();
</script>

<Bits.List
  class={cn(
    'inline-flex h-9 items-center justify-center gap-1 rounded-full border border-border/60 bg-muted/60 p-1 text-muted-foreground backdrop-blur-sm',
    className
  )}
>
  {@render children()}
</Bits.List>
