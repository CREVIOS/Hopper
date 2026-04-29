<script lang="ts" module>
  import { Select as Bits } from 'bits-ui';
  import Trigger from './select-trigger.svelte';
  import Content from './select-content.svelte';
  import Item from './select-item.svelte';

  export const Select = {
    Root: Bits.Root,
    Trigger,
    Content,
    Item,
    Group: Bits.Group,
    GroupHeading: Bits.GroupHeading
  };
</script>
