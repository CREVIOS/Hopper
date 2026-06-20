<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { SvelteComponent } from 'svelte';
  import { cn } from '$lib/utils';

  type IconLike = unknown;

  let {
    title,
    description,
    icon,
    action,
    class: className
  }: {
    title: string;
    description?: string;
    icon?: IconLike;
    action?: Snippet;
    class?: string;
  } = $props();
</script>

<div class={cn('flex items-end justify-between gap-3', className)}>
  <div class="min-w-0">
    <h2 class="flex items-center gap-2 text-lg font-semibold tracking-tight">
      {#if icon}
        {@const Icon = icon as unknown as typeof SvelteComponent}
        <span
          class="flex size-6 items-center justify-center rounded-md bg-primary/10 text-primary"
        >
          <Icon class="size-3.5" />
        </span>
      {/if}
      {title}
    </h2>
    {#if description}
      <p class="mt-0.5 text-sm text-muted-foreground">{description}</p>
    {/if}
  </div>
  {#if action}
    <div class="shrink-0">
      {@render action()}
    </div>
  {/if}
</div>
