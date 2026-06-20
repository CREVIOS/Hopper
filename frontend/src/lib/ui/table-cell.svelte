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

<td
  class={cn('px-4 py-2.5 align-middle [&:has([role=checkbox])]:pr-0', className)}
  {...rest}
>
  {@render children()}
</td>
