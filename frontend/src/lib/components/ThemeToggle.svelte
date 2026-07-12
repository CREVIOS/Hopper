<script lang="ts">
  import { Moon, Sun, Monitor } from 'lucide-svelte';
  import { setMode, mode } from 'mode-watcher';

  let open = $state(false);
  let triggerEl: HTMLButtonElement | null = null;
  let menuEl: HTMLDivElement | null = null;

  function closeMenu() {
    open = false;
  }

  function handleOutsideClick(event: MouseEvent) {
    const target = event.target;
    if (!(target instanceof Node)) return;
    if (triggerEl?.contains(target) || menuEl?.contains(target)) return;
    closeMenu();
  }

  function handleTriggerKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeMenu();
      triggerEl?.focus();
      return;
    }

    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      open = true;
    }
  }

  function handleMenuKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeMenu();
      triggerEl?.focus();
    }
  }
</script>

<svelte:window on:click={handleOutsideClick} on:keydown={handleMenuKeydown} />

<div class="relative">
  <button
    bind:this={triggerEl}
    type="button"
    aria-label="Toggle theme"
    aria-haspopup="menu"
    aria-expanded={open}
    class="inline-flex size-9 items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-all hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    onclick={() => (open = !open)}
    onkeydown={handleTriggerKeydown}
  >
    {#if mode.current === 'dark'}
      <Moon class="size-4" />
    {:else}
      <Sun class="size-4" />
    {/if}
  </button>

  {#if open}
    <div
      bind:this={menuEl}
      role="menu"
      class="absolute right-0 z-50 mt-2 min-w-32 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-lg"
    >
      <button
        type="button"
        role="menuitem"
        class="relative flex w-full cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent"
        onclick={() => {
          closeMenu();
          setMode('light');
        }}
      >
        <Sun class="size-4" /> Light
      </button>
      <button
        type="button"
        role="menuitem"
        class="relative flex w-full cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent"
        onclick={() => {
          closeMenu();
          setMode('dark');
        }}
      >
        <Moon class="size-4" /> Dark
      </button>
      <button
        type="button"
        role="menuitem"
        class="relative flex w-full cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent"
        onclick={() => {
          closeMenu();
          setMode('system');
        }}
      >
        <Monitor class="size-4" /> System
      </button>
    </div>
  {/if}
</div>
