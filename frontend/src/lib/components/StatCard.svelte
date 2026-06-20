<script lang="ts">
  import type { SvelteComponent } from 'svelte';
  import { Card } from '$lib/ui';
  import { cn } from '$lib/utils';

  // lucide-svelte icons have rich prop types; accept any Svelte component
  // so callers can pass them without ceremony.
  type IconLike = unknown;

  let {
    label,
    value,
    sub,
    icon,
    tone = 'default',
    href,
    class: className
  }: {
    label: string;
    value: string | number;
    sub?: string;
    icon?: IconLike;
    tone?: 'default' | 'primary' | 'success' | 'warning' | 'destructive' | 'info';
    href?: string;
    class?: string;
  } = $props();

  const toneMap: Record<string, string> = {
    default: 'text-foreground',
    primary: 'text-primary',
    success: 'text-success',
    warning: 'text-warning',
    destructive: 'text-destructive',
    info: 'text-info'
  };

  // Gradient icon chip + matching text, tinted by tone.
  const ringMap: Record<string, string> = {
    default: 'from-muted to-muted/60 text-muted-foreground',
    primary: 'from-primary/20 to-primary/5 text-primary',
    success: 'from-success/20 to-success/5 text-success',
    warning: 'from-warning/20 to-warning/5 text-warning',
    destructive: 'from-destructive/20 to-destructive/5 text-destructive',
    info: 'from-info/20 to-info/5 text-info'
  };

  // Faint full-card wash so each card reads as its own tone, modestly.
  const surfaceMap: Record<string, string> = {
    default: 'to-muted/30',
    primary: 'to-primary/[0.06]',
    success: 'to-success/[0.06]',
    warning: 'to-warning/[0.06]',
    destructive: 'to-destructive/[0.06]',
    info: 'to-info/[0.06]'
  };

  // Left accent rail in tone color — small, vibrant, on-theme.
  const railMap: Record<string, string> = {
    default: 'bg-muted-foreground/20',
    primary: 'bg-primary',
    success: 'bg-success',
    warning: 'bg-warning',
    destructive: 'bg-destructive',
    info: 'bg-info'
  };
</script>

{#snippet body()}
  <span
    class={cn(
      'absolute inset-y-0 left-0 w-1 opacity-70 transition-opacity group-hover:opacity-100',
      railMap[tone]
    )}
  ></span>
  <div class="relative flex items-start justify-between gap-3 pl-2">
    <div class="min-w-0">
      <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p class={cn('mt-2 text-3xl font-bold tracking-tight tabular-nums', toneMap[tone])}>
        {value}
      </p>
      {#if sub}
        <p class="mt-1 text-xs text-muted-foreground">{sub}</p>
      {/if}
    </div>
    {#if icon}
      {@const Icon = icon as unknown as typeof SvelteComponent}
      <div
        class={cn(
          'flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br shadow-sm ring-1 ring-inset ring-border/50 transition-transform duration-200 group-hover:scale-110',
          ringMap[tone]
        )}
      >
        <Icon class="size-5" />
      </div>
    {/if}
  </div>
{/snippet}

{#if href}
  <a {href} class="group block h-full">
    <Card
      class={cn(
        'card-lift relative h-full overflow-hidden bg-gradient-to-br from-card p-4 hover:border-primary/40 hover:shadow-md',
        surfaceMap[tone],
        className
      )}
    >
      {@render body()}
    </Card>
  </a>
{:else}
  <Card
    class={cn(
      'card-lift group relative h-full overflow-hidden bg-gradient-to-br from-card p-4 hover:border-primary/40 hover:shadow-md',
      surfaceMap[tone],
      className
    )}
  >
    {@render body()}
  </Card>
{/if}
