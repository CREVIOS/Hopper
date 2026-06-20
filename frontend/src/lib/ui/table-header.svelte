<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLAttributes } from 'svelte/elements';
  import { cn } from '$lib/utils';

  type Props = {
    class?: string;
    children: Snippet;
  } & Omit<HTMLAttributes<HTMLTableSectionElement>, 'class' | 'children'>;

  let { class: className, children, ...rest }: Props = $props();
</script>

<thead class={cn('[&_tr]:border-b', className)} {...rest}>
  {@render children()}
</thead>
