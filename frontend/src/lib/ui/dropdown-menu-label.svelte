<script lang="ts">
  import { DropdownMenu as Bits } from 'bits-ui';
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    children,
    class: className
  }: { children: Snippet; class?: string } = $props();
</script>

<Bits.GroupHeading
  class={cn('px-2 py-1.5 text-xs font-semibold text-muted-foreground', className)}
>
  {@render children()}
</Bits.GroupHeading>
