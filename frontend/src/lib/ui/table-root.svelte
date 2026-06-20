<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLAttributes } from 'svelte/elements';
  import { cn } from '$lib/utils';

  type Props = {
    class?: string;
    containerClass?: string;
    children: Snippet;
  } & Omit<HTMLAttributes<HTMLTableElement>, 'class' | 'children'>;

  let { class: className, containerClass, children, ...rest }: Props = $props();
</script>

<div class={cn('relative w-full overflow-auto', containerClass)}>
  <table class={cn('w-full caption-bottom text-sm', className)} {...rest}>
    {@render children()}
  </table>
</div>
