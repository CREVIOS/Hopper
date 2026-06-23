<script lang="ts">
  import { Tabs as Bits } from 'bits-ui';
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    children,
    value,
    class: className
  }: { children: Snippet; value: string; class?: string } = $props();
</script>

<Bits.Trigger
  {value}
  class={cn(
    'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1 text-sm font-medium transition-all duration-200',
    'text-muted-foreground hover:text-foreground',
    'ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
    'disabled:pointer-events-none disabled:opacity-50',
    'data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm data-[state=active]:ring-1 data-[state=active]:ring-border/50',
    '[&_svg]:size-4',
    className
  )}
>
  {@render children()}
</Bits.Trigger>
