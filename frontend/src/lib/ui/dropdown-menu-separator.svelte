<script lang="ts">
  import { DropdownMenu as Bits } from 'bits-ui';
  import { cn } from '$lib/utils';

  let { class: className }: { class?: string } = $props();
</script>

<Bits.Separator class={cn('-mx-1 my-1 h-px bg-border', className)} />
