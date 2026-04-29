<script lang="ts">
  import { Moon, Sun, Monitor } from 'lucide-svelte';
  import { setMode, mode } from 'mode-watcher';
  import { Button, DropdownMenu } from '$lib/ui';
</script>

<DropdownMenu.Root>
  <DropdownMenu.Trigger>
    {#snippet child({ props })}
      <Button {...props} variant="ghost" size="icon" aria-label="Toggle theme">
        {#if mode.current === 'dark'}
          <Moon class="size-4" />
        {:else}
          <Sun class="size-4" />
        {/if}
      </Button>
    {/snippet}
  </DropdownMenu.Trigger>
  <DropdownMenu.Content align="end">
    <DropdownMenu.Item onclick={() => setMode('light')}>
      <Sun class="size-4" /> Light
    </DropdownMenu.Item>
    <DropdownMenu.Item onclick={() => setMode('dark')}>
      <Moon class="size-4" /> Dark
    </DropdownMenu.Item>
    <DropdownMenu.Item onclick={() => setMode('system')}>
      <Monitor class="size-4" /> System
    </DropdownMenu.Item>
  </DropdownMenu.Content>
</DropdownMenu.Root>
