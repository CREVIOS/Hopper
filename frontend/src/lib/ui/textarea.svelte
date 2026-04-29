<script lang="ts">
  import type { HTMLTextareaAttributes } from 'svelte/elements';
  import { cn } from '$lib/utils';

  type Props = HTMLTextareaAttributes & { class?: string; value?: string | null };
  let { class: className, value = $bindable(), ...rest }: Props = $props();
</script>

<textarea
  class={cn(
    'flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm',
    'placeholder:text-muted-foreground',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
    'disabled:cursor-not-allowed disabled:opacity-50',
    className
  )}
  bind:value
  {...rest}
></textarea>
