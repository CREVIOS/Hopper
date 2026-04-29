<script lang="ts">
  import { Progress as ProgressPrimitive } from 'bits-ui';
  import { cn } from '$lib/utils';

  let {
    value = 0,
    max = 100,
    class: className,
    indicatorClass
  }: {
    value?: number | null;
    max?: number;
    class?: string;
    indicatorClass?: string;
  } = $props();

  const pct = $derived(Math.max(0, Math.min(100, ((value ?? 0) / max) * 100)));
</script>

<ProgressPrimitive.Root
  {value}
  {max}
  class={cn(
    'relative h-2 w-full overflow-hidden rounded-full bg-secondary',
    className
  )}
>
  <div
    class={cn(
      'h-full w-full rounded-full bg-primary transition-all duration-700 ease-out',
      indicatorClass
    )}
    style="transform: translateX(-{100 - pct}%)"
  ></div>
</ProgressPrimitive.Root>
