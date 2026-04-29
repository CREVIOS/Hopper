<script lang="ts">
  import { DropdownMenu as Bits } from 'bits-ui';
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    children,
    class: className,
    sideOffset = 6,
    align = 'end'
  }: {
    children: Snippet;
    class?: string;
    sideOffset?: number;
    align?: 'start' | 'center' | 'end';
  } = $props();
</script>

<Bits.Portal>
  <Bits.Content
    {sideOffset}
    {align}
    class={cn(
      'z-50 min-w-[8rem] overflow-hidden rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-lg',
      'data-[state=open]:animate-in data-[state=closed]:animate-out',
      className
    )}
  >
    {@render children()}
  </Bits.Content>
</Bits.Portal>
