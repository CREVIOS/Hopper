<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLAttributes } from 'svelte/elements';
  import { cn } from '$lib/utils';

  type Props = {
    class?: string;
    children: Snippet;
  } & Omit<HTMLAttributes<HTMLTableRowElement>, 'class' | 'children'>;

  let { class: className, children, ...rest }: Props = $props();
</script>

<tr
  class={cn(
    'border-b border-border transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted',
    className
  )}
  {...rest}
>
  {@render children()}
</tr>
