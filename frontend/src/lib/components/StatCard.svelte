<script lang="ts">
  import type { SvelteComponent } from 'svelte';
  import { cn } from '$lib/utils';

  // lucide-svelte icons have rich prop types; accept any Svelte component.
  type IconLike = unknown;

  let {
    label,
    value,
    sub,
    icon,
    tone = 'default',
    href,
    compact = false,
    class: className
  }: {
    label: string;
    value: string | number;
    sub?: string;
    icon?: IconLike;
    tone?: 'default' | 'primary' | 'success' | 'warning' | 'destructive' | 'info';
    href?: string;
    /** Denser layout — smaller padding, value, and icon chip. */
    compact?: boolean;
    class?: string;
  } = $props();

  // Soft tinted icon chip — clean, flat, no gradient wash.
  const iconBox: Record<string, string> = {
    default: 'bg-muted text-muted-foreground',
    primary: 'bg-primary/10 text-primary',
    success: 'bg-success/10 text-success',
    warning: 'bg-warning/10 text-warning',
    destructive: 'bg-destructive/10 text-destructive',
    info: 'bg-info/10 text-info'
  };
</script>

{#snippet body()}
  <div class={cn('flex items-start justify-between', compact ? 'gap-2' : 'gap-3')}>
    <p
      class={cn(
        'font-semibold uppercase tracking-wide text-muted-foreground',
        compact ? 'text-[10px]' : 'text-[11px]'
      )}
    >
      {label}
    </p>
    {#if icon}
      {@const Icon = icon as unknown as typeof SvelteComponent}
      <div
        class={cn(
          'grid shrink-0 place-items-center rounded-lg',
          compact ? 'size-8' : 'size-9',
          iconBox[tone]
        )}
      >
        <Icon class={compact ? 'size-[17px]' : 'size-[18px]'} />
      </div>
    {/if}
  </div>
  <p
    class={cn(
      'font-bold tracking-tight tabular-nums text-foreground',
      compact ? 'mt-2 text-xl' : 'mt-3 text-[1.75rem] leading-none'
    )}
  >
    {value}
  </p>
  {#if sub}
    <p class={cn('text-muted-foreground', compact ? 'mt-1 text-[11px]' : 'mt-2 text-xs')}>
      {sub}
    </p>
  {/if}
{/snippet}

{#if href}
  <a {href} class="group block h-full">
    <div
      class={cn(
        'h-full rounded-xl border border-border bg-card shadow-sm transition-all duration-200 group-hover:-translate-y-0.5 group-hover:border-primary/30 group-hover:shadow-md',
        compact ? 'p-4' : 'p-5',
        className
      )}
    >
      {@render body()}
    </div>
  </a>
{:else}
  <div
    class={cn(
      'h-full rounded-xl border border-border bg-card shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md',
      compact ? 'p-4' : 'p-5',
      className
    )}
  >
    {@render body()}
  </div>
{/if}
