<script lang="ts" module>
  import { Tabs as Bits } from 'bits-ui';
  import List from './tabs-list.svelte';
  import Trigger from './tabs-trigger.svelte';
  import Content from './tabs-content.svelte';

  export const Tabs = {
    Root: Bits.Root,
    List,
    Trigger,
    Content
  };
</script>
