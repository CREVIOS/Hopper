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

<Bits.Content
  {value}
  class={cn(
    'mt-3 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
    className
  )}
>
  {@render children()}
</Bits.Content>
