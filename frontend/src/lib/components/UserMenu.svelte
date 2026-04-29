<script lang="ts">
  import { LogOut, KeyRound, ChevronDown, Shield } from 'lucide-svelte';
  import { goto } from '$app/navigation';
  import { Avatar, DropdownMenu } from '$lib/ui';
  import type { User } from '$lib/types';

  let { user }: { user: User } = $props();

  const isAdmin = $derived(user.role === 'admin' || user.role === 'professor');

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
    window.location.href = '/login';
  }
</script>

<DropdownMenu.Root>
  <DropdownMenu.Trigger>
    {#snippet child({ props })}
      <button
        {...props}
        class="flex items-center gap-2 rounded-full px-1 py-1 pr-2 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Avatar name={user.name || user.email} />
        <span class="hidden text-left sm:block">
          <span class="block text-sm font-medium leading-tight">{user.name}</span>
          <span class="block text-xs text-muted-foreground leading-tight"
            >{user.role}</span
          >
        </span>
        <ChevronDown class="size-4 text-muted-foreground hidden sm:block" />
      </button>
    {/snippet}
  </DropdownMenu.Trigger>
  <DropdownMenu.Content align="end" class="min-w-56">
    <DropdownMenu.Label>
      <div>
        <div class="text-foreground font-medium">{user.name || 'User'}</div>
        <div class="font-normal text-muted-foreground truncate">{user.email}</div>
      </div>
    </DropdownMenu.Label>
    <DropdownMenu.Separator />
    <DropdownMenu.Item onclick={() => goto('/settings/ssh-keys')}>
      <KeyRound class="size-4" /> SSH Keys
    </DropdownMenu.Item>
    {#if isAdmin}
      <DropdownMenu.Item onclick={() => goto('/admin')}>
        <Shield class="size-4" /> Admin console
      </DropdownMenu.Item>
    {/if}
    <DropdownMenu.Separator />
    <DropdownMenu.Item danger onclick={logout}>
      <LogOut class="size-4" /> Sign out
    </DropdownMenu.Item>
  </DropdownMenu.Content>
</DropdownMenu.Root>
