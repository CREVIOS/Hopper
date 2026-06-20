<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { SvelteComponent } from 'svelte';
  import { cn } from '$lib/utils';

  type IconLike = unknown;

  let {
    title,
    description,
    eyebrow,
    eyebrowIcon,
    action,
    class: className
  }: {
    title: string;
    description?: string;
    eyebrow?: string;
    eyebrowIcon?: IconLike;
    action?: Snippet;
    class?: string;
  } = $props();
</script>

<div
  class={cn(
    'animate-fade-up flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between',
    className
  )}
>
  <div class="min-w-0">
    {#if eyebrow}
      <div
        class="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs font-medium text-muted-foreground"
      >
        {#if eyebrowIcon}
          {@const Icon = eyebrowIcon as unknown as typeof SvelteComponent}
          <Icon class="size-3 text-primary" />
        {/if}
        {eyebrow}
      </div>
    {/if}
    <h1
      class={cn(
        'text-3xl font-bold tracking-tight',
        eyebrow ? 'mt-2' : ''
      )}
    >
      {title}
    </h1>
    {#if description}
      <p class="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>
    {/if}
  </div>
  {#if action}
    <div class="shrink-0">
      {@render action()}
    </div>
  {/if}
</div>
