<script lang="ts">
  import { LogOut, KeyRound, ChevronDown, Shield } from 'lucide-svelte';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { Avatar } from '$lib/ui';
  import type { User } from '$lib/types';

  let { user }: { user: User } = $props();
  let hydrated = $state(false);
  let open = $state(false);
  let triggerEl: HTMLButtonElement | null = null;
  let menuEl: HTMLDivElement | null = null;

  onMount(() => {
    hydrated = true;
  });

  const isAdmin = $derived(user.role === 'admin' || user.role === 'professor');

  // Human-friendly role label. A "teacher" signup stays role=student until an
  // admin approves, so show the pending state instead of a bare "student".
  const roleLabel = $derived.by(() => {
    if (user.pending_teacher) return 'Teacher · pending approval';
    if (user.role === 'professor') return 'Teacher';
    return user.role.charAt(0).toUpperCase() + user.role.slice(1);
  });

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

  async function logout() {
    closeMenu();
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
    window.location.href = '/login';
  }

  function runAction(action: () => void | Promise<void>) {
    return async () => {
      closeMenu();
      await action();
    };
  }
</script>

<svelte:window on:click={handleOutsideClick} on:keydown={handleMenuKeydown} />

<div class="relative">
  <button
    bind:this={triggerEl}
    type="button"
    aria-label={`User menu for ${user.name || user.email}`}
    aria-haspopup="menu"
    aria-expanded={open}
    data-hydrated={hydrated}
    class="inline-flex h-auto items-center gap-2 rounded-full px-1 py-1 pr-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    onclick={() => (open = !open)}
    onkeydown={handleTriggerKeydown}
  >
    <Avatar name={user.name || user.email} />
    <span class="hidden text-left sm:block">
      <span class="block text-sm font-medium leading-tight">{user.name}</span>
      <span
        class="block text-xs leading-tight {user.pending_teacher
          ? 'text-warning'
          : 'text-muted-foreground'}">{roleLabel}</span
      >
    </span>
    <ChevronDown class="size-4 text-muted-foreground hidden sm:block" />
  </button>

  {#if open}
    <div
      bind:this={menuEl}
      role="menu"
      class="absolute right-0 z-50 mt-2 min-w-56 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-lg"
    >
      <div class="px-2 py-1.5">
        <div class="text-foreground font-medium">{user.name || 'User'}</div>
        <div class="truncate font-normal text-muted-foreground">{user.email}</div>
      </div>
      <div class="my-1 h-px bg-border"></div>
      <button
        type="button"
        role="menuitem"
        class="relative flex w-full cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent"
        onclick={runAction(() => goto('/settings/ssh-keys'))}
      >
        <KeyRound class="size-4" /> SSH Keys
      </button>
      {#if isAdmin}
        <button
          type="button"
          role="menuitem"
          class="relative flex w-full cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent"
          onclick={runAction(() => goto('/admin'))}
        >
          <Shield class="size-4" /> Admin console
        </button>
      {/if}
      <div class="my-1 h-px bg-border"></div>
      <button
        type="button"
        role="menuitem"
        class="relative flex w-full cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors text-destructive hover:bg-destructive/10 hover:text-destructive focus:bg-destructive/10 focus:text-destructive"
        onclick={logout}
      >
        <LogOut class="size-4" /> Sign out
      </button>
    </div>
  {/if}
</div>
