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
    onclick?: (e: MouseEvent) => void;
    disabled?: boolean;
  } = $props();
</script>

<Bits.Item
  {disabled}
  {onclick}
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
