<script lang="ts" module>
  // Re-export the bits-ui DropdownMenu primitive parts under a single namespace
  // alongside our pre-styled Content/Item/Label/Separator wrappers.
  import { DropdownMenu as Bits } from 'bits-ui';
  import Content from './dropdown-menu-content.svelte';
  import Item from './dropdown-menu-item.svelte';
  import LabelEl from './dropdown-menu-label.svelte';
  import SeparatorEl from './dropdown-menu-separator.svelte';

  export const DropdownMenu = {
    Root: Bits.Root,
    Trigger: Bits.Trigger,
    Group: Bits.Group,
    Sub: Bits.Sub,
    SubTrigger: Bits.SubTrigger,
    Portal: Bits.Portal,
    Content,
    Item,
    Label: LabelEl,
    Separator: SeparatorEl
  };
</script>
