<script lang="ts">
  import { AlertDialog } from '$lib/ui';
  import { confirmStore, _resolveConfirm } from '$lib/confirm.svelte';

  // Mounted once in the root layout. Any caller of confirm() drives this
  // dialog through the shared store. Closing via cancel/X resolves false;
  // confirming resolves true.
  function onConfirm() {
    _resolveConfirm(true);
  }

  function onCancel() {
    _resolveConfirm(false);
  }

  // bits-ui closes on outside click / escape — bridge that into the promise.
  $effect(() => {
    if (!confirmStore.open && confirmStore.resolve) {
      _resolveConfirm(false);
    }
  });
</script>

<AlertDialog
  bind:open={confirmStore.open}
  title={confirmStore.title}
  description={confirmStore.description}
  confirmLabel={confirmStore.confirmLabel}
  cancelLabel={confirmStore.cancelLabel}
  confirmVariant={confirmStore.variant}
  {onConfirm}
  {onCancel}
/>
