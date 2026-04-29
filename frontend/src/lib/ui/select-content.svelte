<script lang="ts">
  import { Select as Bits } from 'bits-ui';
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    children,
    class: className,
    sideOffset = 4
  }: { children: Snippet; class?: string; sideOffset?: number } = $props();
</script>

<Bits.Portal>
  <Bits.Content
    {sideOffset}
    class={cn(
      'relative z-50 max-h-[40vh] min-w-[8rem] overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-lg',
      'data-[state=open]:animate-in data-[state=closed]:animate-out',
      className
    )}
  >
    <Bits.Viewport class="p-1">
      {@render children()}
    </Bits.Viewport>
  </Bits.Content>
</Bits.Portal>
