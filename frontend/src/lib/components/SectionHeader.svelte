<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { SvelteComponent } from 'svelte';
  import { cn } from '$lib/utils';

  type IconLike = unknown;

  let {
    title,
    description,
    icon,
    badge,
    action,
    class: className
  }: {
    title: string;
    description?: string;
    icon?: IconLike;
    /** Optional element rendered inline beside the title — e.g. a count <Badge>. */
    badge?: Snippet;
    action?: Snippet;
    class?: string;
  } = $props();
</script>

<div class={cn('flex items-end justify-between gap-3', className)}>
  <div class="min-w-0">
    <h2 class="flex flex-wrap items-center gap-2 text-lg font-semibold tracking-tight">
      {#if icon}
        {@const Icon = icon as unknown as typeof SvelteComponent}
        <span
          class="flex size-6 items-center justify-center rounded-md bg-primary/10 text-primary"
        >
          <Icon class="size-3.5" />
        </span>
      {/if}
      {title}
      {#if badge}
        {@render badge()}
      {/if}
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
