<script lang="ts">
  import { Switch as SwitchPrimitive } from 'bits-ui';
  import { cn } from '$lib/utils';

  let {
    checked = $bindable(false),
    class: className,
    ...rest
  }: { checked?: boolean; class?: string; [key: string]: unknown } = $props();
</script>

<SwitchPrimitive.Root
  bind:checked
  class={cn(
    'peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
    'disabled:cursor-not-allowed disabled:opacity-50',
    'data-[state=checked]:bg-primary data-[state=unchecked]:bg-muted',
    className
  )}
  {...rest}
>
  <SwitchPrimitive.Thumb
    class={cn(
      'pointer-events-none block size-4 rounded-full bg-background shadow ring-0 transition-transform',
      'data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0'
    )}
  />
</SwitchPrimitive.Root>
