<script lang="ts">
  import { Tooltip as Bits } from 'bits-ui';
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    content,
    children,
    side = 'top',
    delay = 200,
    class: className
  }: {
    content: string;
    children: Snippet<[Record<string, unknown>]>;
    side?: 'top' | 'right' | 'bottom' | 'left';
    delay?: number;
    class?: string;
  } = $props();
</script>

<Bits.Provider delayDuration={delay}>
  <Bits.Root>
    <Bits.Trigger>
      {#snippet child({ props })}
        {@render children(props)}
      {/snippet}
    </Bits.Trigger>
    <Bits.Portal>
      <Bits.Content
        {side}
        sideOffset={6}
        class={cn(
          'z-50 overflow-hidden rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background shadow-md',
          'data-[state=delayed-open]:animate-in',
          className
        )}
      >
        {content}
      </Bits.Content>
    </Bits.Portal>
  </Bits.Root>
</Bits.Provider>
