<script lang="ts">
  import { DropdownMenu as Bits } from 'bits-ui';
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    children,
    class: className,
    danger = false,
    onclick,
    disabled
  }: {
    children: Snippet;
    class?: string;
    danger?: boolean;
    onclick?: (e: Event) => void;
    disabled?: boolean;
  } = $props();

  // bits-ui v2 Menu.Item uses `onSelect`, not native `onclick`. The menu
  // intercepts clicks on its own to fire selection + close in one step, so a
  // plain `onclick` either misses the event or races the portal teardown
  // (which is what made the admin/user-menu buttons appear unresponsive).
  // We forward our public `onclick` prop to `onSelect` so call sites don't
  // need to change.
</script>

<Bits.Item
  {disabled}
  onSelect={onclick}
  class={cn(
    'relative flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors',
    'focus:bg-accent focus:text-accent-foreground',
    'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
    danger && 'text-destructive focus:bg-destructive/10 focus:text-destructive',
    className
  )}
>
  {@render children()}
</Bits.Item>
