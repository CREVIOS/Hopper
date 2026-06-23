<script lang="ts" module>
  export type PageItem = number | 'ellipsis';

  /** Build a compact page list: 1 … (p-1) p (p+1) … N, with first/last pinned. */
  export function buildPageList(
    current: number,
    total: number,
    sibling = 1
  ): PageItem[] {
    if (total <= 1) return [1];
    const pages: PageItem[] = [];
    const left = Math.max(2, current - sibling);
    const right = Math.min(total - 1, current + sibling);
    pages.push(1);
    if (left > 2) pages.push('ellipsis');
    for (let i = left; i <= right; i++) pages.push(i);
    if (right < total - 1) pages.push('ellipsis');
    pages.push(total);
    return pages;
  }
</script>

<script lang="ts">
  import { ChevronLeft, ChevronRight } from 'lucide-svelte';
  import { cn } from '$lib/utils';
  import { buttonVariants } from './button.svelte';

  let {
    count,
    perPage = 25,
    page = $bindable(1),
    siblingCount = 1,
    showSummary = true,
    itemLabel = 'item',
    itemLabelPlural,
    class: className
  }: {
    /** total number of items across all pages */
    count: number;
    perPage?: number;
    /** current 1-based page (bindable) */
    page?: number;
    siblingCount?: number;
    showSummary?: boolean;
    /** singular noun for the summary, e.g. "entry" / "VM" */
    itemLabel?: string;
    /** explicit plural; otherwise derived (entry→entries, VM→VMs) */
    itemLabelPlural?: string;
    class?: string;
  } = $props();

  const totalPages = $derived(Math.max(1, Math.ceil(count / perPage)));

  // Keep page in range when count/perPage change underneath us.
  $effect(() => {
    if (page > totalPages) page = totalPages;
    else if (page < 1) page = 1;
  });

  const pages = $derived(buildPageList(page, totalPages, siblingCount));
  const start = $derived(count === 0 ? 0 : (page - 1) * perPage + 1);
  const end = $derived(Math.min(count, page * perPage));
  const plural = $derived(
    itemLabelPlural ??
      (/[^aeiou]y$/i.test(itemLabel)
        ? `${itemLabel.slice(0, -1)}ies`
        : itemLabel.endsWith('s')
          ? itemLabel
          : `${itemLabel}s`)
  );

  function go(p: number) {
    page = Math.min(totalPages, Math.max(1, p));
  }
</script>

{#if totalPages > 1 || showSummary}
  <nav
    class={cn(
      'flex flex-col items-center justify-between gap-3 sm:flex-row',
      className
    )}
    aria-label="Pagination"
  >
    {#if showSummary}
      <p class="text-xs text-muted-foreground" aria-live="polite">
        {start}–{end} of {count}
        {count === 1 ? itemLabel : plural}
      </p>
    {/if}

    {#if totalPages > 1}
      <div class="flex items-center gap-1">
        <button
          type="button"
          class={cn(
            buttonVariants({ variant: 'outline', size: 'icon' }),
            'size-8'
          )}
          onclick={() => go(page - 1)}
          disabled={page === 1}
          aria-label="Previous page"
        >
          <ChevronLeft class="size-4" />
        </button>

        {#each pages as p, i (typeof p === 'number' ? `p${p}` : `e${i}`)}
          {#if p === 'ellipsis'}
            <span
              class="flex size-8 items-center justify-center text-sm text-muted-foreground"
              aria-hidden="true">…</span
            >
          {:else}
            <button
              type="button"
              class={cn(
                buttonVariants({
                  variant: p === page ? 'default' : 'outline',
                  size: 'icon'
                }),
                'size-8 text-xs tabular-nums'
              )}
              aria-current={p === page ? 'page' : undefined}
              aria-label={`Page ${p}`}
              onclick={() => go(p)}
            >
              {p}
            </button>
          {/if}
        {/each}

        <button
          type="button"
          class={cn(
            buttonVariants({ variant: 'outline', size: 'icon' }),
            'size-8'
          )}
          onclick={() => go(page + 1)}
          disabled={page === totalPages}
          aria-label="Next page"
        >
          <ChevronRight class="size-4" />
        </button>
      </div>
    {/if}
  </nav>
{/if}
