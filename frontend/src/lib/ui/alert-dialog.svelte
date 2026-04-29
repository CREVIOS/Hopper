<script lang="ts">
  import { AlertDialog as AlertDialogPrimitive } from 'bits-ui';
  import { fade, scale } from 'svelte/transition';
  import type { Snippet } from 'svelte';
  import { cn } from '$lib/utils';
  import { buttonVariants, type ButtonVariant } from './button.svelte';

  let {
    open = $bindable(false),
    title,
    description,
    confirmLabel = 'Continue',
    cancelLabel = 'Cancel',
    confirmVariant = 'default',
    onConfirm,
    onCancel,
    body,
    class: className
  }: {
    open?: boolean;
    title: string;
    description?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    confirmVariant?: ButtonVariant;
    onConfirm?: () => void | Promise<void>;
    onCancel?: () => void;
    body?: Snippet;
    class?: string;
  } = $props();

  let busy = $state(false);
  async function handleConfirm() {
    if (busy) return;
    busy = true;
    try {
      await onConfirm?.();
      open = false;
    } finally {
      busy = false;
    }
  }
</script>

<AlertDialogPrimitive.Root bind:open>
  <AlertDialogPrimitive.Portal>
    <AlertDialogPrimitive.Overlay forceMount>
      {#snippet child({ props, open })}
        {#if open}
          <div
            {...props}
            class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            transition:fade={{ duration: 150 }}
          ></div>
        {/if}
      {/snippet}
    </AlertDialogPrimitive.Overlay>
    <AlertDialogPrimitive.Content forceMount>
      {#snippet child({ props, open })}
        {#if open}
          <div
            {...props}
            class={cn(
              'fixed left-[50%] top-[50%] z-50 grid w-full max-w-md translate-x-[-50%] translate-y-[-50%] gap-4 border border-border bg-card p-6 shadow-2xl rounded-xl',
              className
            )}
            in:scale={{ start: 0.95, duration: 180 }}
            out:scale={{ start: 0.97, duration: 140 }}
          >
            <div class="flex flex-col space-y-2 text-center sm:text-left">
              <AlertDialogPrimitive.Title
                class="text-lg font-semibold tracking-tight"
              >
                {title}
              </AlertDialogPrimitive.Title>
              {#if description}
                <AlertDialogPrimitive.Description
                  class="text-sm text-muted-foreground"
                >
                  {description}
                </AlertDialogPrimitive.Description>
              {/if}
            </div>

            {#if body}
              <div>{@render body()}</div>
            {/if}

            <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <AlertDialogPrimitive.Cancel
                class={cn(buttonVariants({ variant: 'outline' }))}
                onclick={onCancel}
                disabled={busy}
              >
                {cancelLabel}
              </AlertDialogPrimitive.Cancel>
              <AlertDialogPrimitive.Action
                class={cn(buttonVariants({ variant: confirmVariant }))}
                onclick={handleConfirm}
                disabled={busy}
              >
                {busy ? 'Working…' : confirmLabel}
              </AlertDialogPrimitive.Action>
            </div>
          </div>
        {/if}
      {/snippet}
    </AlertDialogPrimitive.Content>
  </AlertDialogPrimitive.Portal>
</AlertDialogPrimitive.Root>
