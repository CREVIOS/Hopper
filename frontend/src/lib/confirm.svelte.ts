import type { ButtonVariant } from './ui/button.svelte';

type ConfirmOptions = {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: ButtonVariant;
};

type ConfirmState = ConfirmOptions & {
  open: boolean;
  resolve: ((value: boolean) => void) | null;
};

// Reactive singleton driven via Svelte 5 runes. Pages call confirm() and
// the global ConfirmHost in the layout renders an AlertDialog tied to this
// state. The promise resolves when the user picks an action.
const state = $state<ConfirmState>({
  open: false,
  title: '',
  resolve: null
});

export const confirmStore = state;

export function confirm(opts: ConfirmOptions): Promise<boolean> {
  if (state.resolve) {
    state.resolve(false);
  }
  Object.assign(state, {
    open: true,
    title: opts.title,
    description: opts.description,
    confirmLabel: opts.confirmLabel ?? 'Continue',
    cancelLabel: opts.cancelLabel ?? 'Cancel',
    variant: opts.variant ?? 'default'
  });
  return new Promise<boolean>((resolve) => {
    state.resolve = resolve;
  });
}

export function _resolveConfirm(value: boolean) {
  state.resolve?.(value);
  state.resolve = null;
  state.open = false;
}
