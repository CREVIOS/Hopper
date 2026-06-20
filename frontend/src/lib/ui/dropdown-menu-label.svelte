<script lang="ts">
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    children,
    class: className
  }: { children: Snippet; class?: string } = $props();

  // bits-ui v2's `Menu.GroupHeading` requires a `Menu.Group` ancestor and
  // throws "Context 'Menu.Group | Menu.RadioGroup' not found" if used
  // directly inside `Menu.Content`. The label here is purely presentational
  // (no keyboard nav, no selection semantics), so we render a plain div and
  // sidestep the Group requirement entirely.
</script>

<div
  role="presentation"
  class={cn('px-2 py-1.5 text-xs font-semibold text-muted-foreground', className)}
>
  {@render children()}
</div>
