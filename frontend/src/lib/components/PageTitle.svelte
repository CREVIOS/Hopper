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
    badge,
    leading,
    action,
    mono = false,
    class: className
  }: {
    /** The page title text. */
    title: string;
    /** Optional supporting line shown beneath the title. */
    description?: string;
    /** Short chip text shown beside the title (e.g. "Settings", "Admin console"). */
    eyebrow?: string;
    /** Optional lucide icon component rendered inside the eyebrow chip. */
    eyebrowIcon?: IconLike;
    /** Free-form badge(s) rendered beside the title — e.g. a <Badge>. */
    badge?: Snippet;
    /** Element placed before the title, e.g. a back button. */
    leading?: Snippet;
    /** Right-aligned actions, e.g. buttons. */
    action?: Snippet;
    /** Render the title in the monospace font (for IDs / technical names). */
    mono?: boolean;
    class?: string;
  } = $props();
</script>

<div
  class={cn(
    'animate-fade-up flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between',
    className
  )}
>
  <div class="flex min-w-0 items-start gap-3">
    {#if leading}
      <div class="shrink-0 pt-0.5">{@render leading()}</div>
    {/if}
    <div class="min-w-0">
      <!-- Title row: badges sit beside the title, never above it. -->
      <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1
          class={cn(
            'text-2xl font-bold tracking-tight text-foreground sm:text-3xl',
            mono && 'font-mono text-xl sm:text-2xl'
          )}
        >
          {title}
        </h1>
        {#if eyebrow}
          <span
            class="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs font-medium text-muted-foreground"
          >
            {#if eyebrowIcon}
              {@const Icon = eyebrowIcon as unknown as typeof SvelteComponent}
              <Icon class="size-3 text-primary" />
            {/if}
            {eyebrow}
          </span>
        {/if}
        {#if badge}
          {@render badge()}
        {/if}
      </div>
      {#if description}
        <p class="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
      {/if}
    </div>
  </div>
  {#if action}
    <div class="shrink-0">
      {@render action()}
    </div>
  {/if}
</div>
