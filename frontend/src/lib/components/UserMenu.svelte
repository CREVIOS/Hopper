<script lang="ts">
  import { LogOut, KeyRound, ChevronDown, Shield, GraduationCap } from 'lucide-svelte';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { Avatar } from '$lib/ui';
  import type { User } from '$lib/types';

  let { user }: { user: User } = $props();
  let hydrated = $state(false);
  let menu: HTMLDetailsElement;

  onMount(() => {
    hydrated = true;
  });

  // Admin console is admin-only (professors are redirected out of /admin);
  // professors get a working Teaching link instead of a dead one.
  const isAdmin = $derived(user.role === 'admin');
  const isTeacher = $derived(user.role === 'professor');

  // Human-friendly role label. A "teacher" signup stays role=student until an
  // admin approves, so show the pending state instead of a bare "student".
  const roleLabel = $derived.by(() => {
    if (user.pending_teacher) return 'Teacher · pending approval';
    if (user.role === 'professor') return 'Teacher';
    return user.role.charAt(0).toUpperCase() + user.role.slice(1);
  });

  function handleMenuKeydown(event: KeyboardEvent) {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    menu.open = false;
    menu.querySelector<HTMLElement>('summary')?.focus();
  }

  async function logout() {
    const response = await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include'
    });
    if (!response.ok) return;

    localStorage.clear();
    sessionStorage.clear();
    window.location.href = '/login';
  }
</script>

<details bind:this={menu} class="relative">
  <!-- svelte-ignore a11y_no_redundant_roles (keeps Chromium's accessibility role stable) -->
  <summary
    role="button"
    aria-label={`User menu for ${user.name || user.email}`}
    aria-haspopup="menu"
    data-hydrated={hydrated}
    class="inline-flex h-auto cursor-pointer list-none items-center gap-2 rounded-full px-1 py-1 pr-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 [&::-webkit-details-marker]:hidden"
    onkeydown={handleMenuKeydown}
  >
    <Avatar name={user.name || user.email} />
    <span class="hidden text-left sm:block">
      <span class="block text-sm font-medium leading-tight">{user.name}</span>
      <span class="block text-xs leading-tight {user.pending_teacher ? 'text-warning' : 'text-muted-foreground'}">{roleLabel}</span>
    </span>
    <ChevronDown class="size-4 text-muted-foreground hidden sm:block" />
  </summary>

    <div role="menu" tabindex="-1" onkeydown={handleMenuKeydown} class="absolute right-0 z-50 mt-2 min-w-56 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-lg">
      <div class="px-2 py-1.5">
        <div class="text-foreground font-medium">{user.name || 'User'}</div>
        <div class="truncate font-normal text-muted-foreground">{user.email}</div>
      </div>
      <div class="my-1 h-px bg-border"></div>
      <button type="button" role="menuitem" class="relative flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent focus:bg-accent" onclick={() => goto('/settings/ssh-keys')}>
        <KeyRound class="size-4" /> SSH Keys
      </button>
      {#if isAdmin}
        <button type="button" role="menuitem" class="relative flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent focus:bg-accent" onclick={() => goto('/admin')}>
          <Shield class="size-4" /> Admin console
        </button>
      {/if}
      {#if isTeacher}
        <button type="button" role="menuitem" class="relative flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent focus:bg-accent" onclick={() => goto('/teacher')}>
          <GraduationCap class="size-4" /> Teaching
        </button>
      {/if}
      <div class="my-1 h-px bg-border"></div>
      <button type="button" role="menuitem" class="relative flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-destructive hover:bg-destructive/10 focus:bg-destructive/10" onclick={logout}>
        <LogOut class="size-4" /> Sign out
      </button>
    </div>
</details>
