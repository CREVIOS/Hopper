<script lang="ts">
  import { Dialog as DialogPrimitive } from 'bits-ui';
  import { fade, scale } from 'svelte/transition';
  import { X } from 'lucide-svelte';
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';

  let {
    open = $bindable(false),
    title,
    description,
    children,
    footer,
    class: className,
    showClose = true
  }: {
    open?: boolean;
    title?: string;
    description?: string;
    children: Snippet;
    footer?: Snippet;
    class?: string;
    showClose?: boolean;
  } = $props();
</script>

<DialogPrimitive.Root bind:open>
  <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay
      forceMount
    >
      {#snippet child({ props, open })}
        {#if open}
          <div
            {...props}
            class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            transition:fade={{ duration: 150 }}
          ></div>
        {/if}
      {/snippet}
    </DialogPrimitive.Overlay>
    <DialogPrimitive.Content
      forceMount
    >
      {#snippet child({ props, open })}
        {#if open}
          <div
            {...props}
            class={cn(
              'fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border border-border bg-card p-6 shadow-2xl rounded-xl',
              className
            )}
            in:scale={{ start: 0.95, duration: 180 }}
            out:scale={{ start: 0.97, duration: 140 }}
          >
            {#if title || description}
              <div class="flex flex-col space-y-1.5">
                {#if title}
                  <DialogPrimitive.Title
                    class="text-lg font-semibold leading-none tracking-tight"
                  >
                    {title}
                  </DialogPrimitive.Title>
                {/if}
                {#if description}
                  <DialogPrimitive.Description
                    class="text-sm text-muted-foreground"
                  >
                    {description}
                  </DialogPrimitive.Description>
                {/if}
              </div>
            {/if}

            {@render children()}

            {#if footer}
              <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                {@render footer()}
              </div>
            {/if}

            {#if showClose}
              <DialogPrimitive.Close
                class="absolute right-4 top-4 rounded-md p-1 opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              >
                <X class="size-4" />
                <span class="sr-only">Close</span>
              </DialogPrimitive.Close>
            {/if}
          </div>
        {/if}
      {/snippet}
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>
</DialogPrimitive.Root>
