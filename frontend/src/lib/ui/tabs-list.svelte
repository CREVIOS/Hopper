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
    'inline-flex h-9 items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground',
    className
  )}
>
  {@render children()}
</Bits.List>
