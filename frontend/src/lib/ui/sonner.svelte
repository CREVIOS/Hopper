<script lang="ts">
  import { Toaster as Sonner, type ToasterProps } from 'svelte-sonner';
  import { mode } from 'mode-watcher';

  let { ...rest }: ToasterProps = $props();
</script>

<Sonner
  theme={mode.current === 'dark' ? 'dark' : 'light'}
  class="toaster group"
  position="top-right"
  richColors
  closeButton
  toastOptions={{
    classes: {
      toast:
        'group toast group-[.toaster]:bg-card group-[.toaster]:text-card-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg',
      description: 'group-[.toast]:text-muted-foreground',
      actionButton:
        'group-[.toast]:bg-primary group-[.toast]:text-primary-foreground',
      cancelButton:
        'group-[.toast]:bg-muted group-[.toast]:text-muted-foreground'
    }
  }}
  {...rest}
/>
