<script lang="ts">
  import { Select as Bits } from 'bits-ui';
  import type { Snippet } from 'svelte';
  import { Check } from 'lucide-svelte';
  import { cn } from '$lib/utils';

  let {
    children,
    value,
    label,
    class: className,
    disabled
  }: {
    children?: Snippet;
    value: string;
    label?: string;
    class?: string;
    disabled?: boolean;
  } = $props();
</script>

<Bits.Item
  {value}
  {label}
  {disabled}
  class={cn(
    'relative flex w-full cursor-pointer select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none transition-colors',
    'focus:bg-accent focus:text-accent-foreground',
    'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
    className
  )}
>
  {#snippet children({ selected })}
    {#if selected}
      <span class="absolute left-2 flex size-3.5 items-center justify-center">
        <Check class="size-4" />
      </span>
    {/if}
    <span>{label ?? value}</span>
  {/snippet}
</Bits.Item>
