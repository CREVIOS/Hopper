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

  const ringMap: Record<string, string> = {
    default: 'bg-muted text-muted-foreground',
    primary: 'bg-primary/10 text-primary',
    success: 'bg-success/10 text-success',
    warning: 'bg-warning/10 text-warning',
    destructive: 'bg-destructive/10 text-destructive',
    info: 'bg-info/10 text-info'
  };
</script>

{#snippet body()}
  <div class="flex items-start justify-between">
    <div>
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
      <div class={cn('flex size-10 items-center justify-center rounded-xl', ringMap[tone])}>
        <Icon class="size-5" />
      </div>
    {/if}
  </div>
{/snippet}

{#if href}
  <a {href}>
    <Card class={cn('p-5 transition-all hover:border-primary/40 hover:shadow-md', className)}>
      {@render body()}
    </Card>
  </a>
{:else}
  <Card class={cn('p-5', className)}>
    {@render body()}
  </Card>
{/if}
