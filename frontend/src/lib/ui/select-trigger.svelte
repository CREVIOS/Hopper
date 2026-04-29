<script lang="ts">
  import { Select as Bits } from 'bits-ui';
  import type { Snippet } from 'svelte';
  import { ChevronsUpDown } from 'lucide-svelte';
  import { cn } from '$lib/utils';

  let {
    children,
    class: className,
    placeholder
  }: { children?: Snippet; class?: string; placeholder?: string } = $props();
</script>

<Bits.Trigger
  class={cn(
    'flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm',
    'ring-offset-background placeholder:text-muted-foreground',
    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
    'disabled:cursor-not-allowed disabled:opacity-50',
    'data-[placeholder]:text-muted-foreground',
    '[&>span]:line-clamp-1',
    className
  )}
>
  {#if children}
    {@render children()}
  {:else if placeholder}
    <span>{placeholder}</span>
  {/if}
  <ChevronsUpDown class="size-4 opacity-50" />
</Bits.Trigger>
