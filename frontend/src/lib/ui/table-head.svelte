<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLAttributes } from 'svelte/elements';
  import { cn } from '$lib/utils';

  type Props = {
    class?: string;
    children: Snippet;
  } & Omit<HTMLAttributes<HTMLTableCellElement>, 'class' | 'children'>;

  let { class: className, children, ...rest }: Props = $props();
</script>

<th
  class={cn(
    'h-10 px-4 text-left align-middle text-xs font-semibold uppercase tracking-wide text-muted-foreground [&:has([role=checkbox])]:pr-0',
    className
  )}
  {...rest}
>
  {@render children()}
</th>
