<script lang="ts">
  import { Bell, CheckCheck } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import {
    notifications,
    unreadCount,
    connectNotifications,
    disconnectNotifications,
    markRead,
    markAllRead
  } from '$lib/stores/notifications';
  import type { AppNotification } from '$lib/types';

  let menu = $state<HTMLDetailsElement>();
  let hydrated = $state(false);

  onMount(() => {
    hydrated = true;
    connectNotifications();
    return () => disconnectNotifications();
  });

  function handleMenuKeydown(event: KeyboardEvent) {
    if (event.key !== 'Escape' || !menu) return;
    event.preventDefault();
    menu.open = false;
    menu.querySelector<HTMLElement>('summary')?.focus();
  }

  function onItemClick(n: AppNotification) {
    void markRead(n.id);
    if (typeof n.data?.pod_id === 'string' && n.data.pod_id) {
      if (menu) menu.open = false;
      goto(`/pods/${n.data.pod_id}`);
    }
  }

  const typeDot: Record<string, string> = {
    success: 'bg-success',
    warning: 'bg-warning',
    error: 'bg-destructive',
    info: 'bg-primary'
  };

  function timeAgo(iso: string): string {
    const then = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z').getTime();
    const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (secs < 60) return 'just now';
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  }
</script>

<details bind:this={menu} class="relative">
  <!-- svelte-ignore a11y_no_redundant_roles (keeps Chromium's accessibility role stable) -->
  <summary
    role="button"
    aria-label={`Notifications${$unreadCount ? ` (${$unreadCount} unread)` : ''}`}
    aria-haspopup="menu"
    data-hydrated={hydrated}
    class="relative inline-flex size-9 cursor-pointer list-none items-center justify-center rounded-md text-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden"
    onkeydown={handleMenuKeydown}
  >
    <Bell class="size-4" />
    {#if $unreadCount > 0}
      <span
        class="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-none text-destructive-foreground"
      >
        {$unreadCount > 99 ? '99+' : $unreadCount}
      </span>
    {/if}
  </summary>

  <div
    role="menu"
    tabindex="-1"
    onkeydown={handleMenuKeydown}
    class="absolute right-0 z-50 mt-2 w-80 rounded-md border border-border bg-popover text-popover-foreground shadow-lg sm:w-96"
  >
    <div class="flex items-center justify-between px-3 py-2">
      <span class="text-sm font-semibold">Notifications</span>
      {#if $unreadCount > 0}
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          onclick={() => markAllRead()}
        >
          <CheckCheck class="size-3.5" /> Mark all read
        </button>
      {/if}
    </div>
    <div class="h-px bg-border"></div>
    <div class="max-h-96 overflow-y-auto p-1">
      {#if $notifications.length === 0}
        <p class="px-3 py-6 text-center text-sm text-muted-foreground">No notifications yet</p>
      {:else}
        {#each $notifications.slice(0, 15) as n (n.id)}
          <button
            type="button"
            role="menuitem"
            class="flex w-full items-start gap-2 rounded-sm px-2 py-2 text-left hover:bg-accent focus:bg-accent"
            onclick={() => onItemClick(n)}
          >
            <span class={`mt-1.5 size-2 shrink-0 rounded-full ${typeDot[n.type] ?? typeDot.info} ${n.read ? 'opacity-25' : ''}`}></span>
            <span class="min-w-0 flex-1">
              <span class={`block truncate text-sm ${n.read ? 'text-muted-foreground' : 'font-medium'}`}>{n.title}</span>
              {#if n.body}
                <span class="block text-xs text-muted-foreground line-clamp-2">{n.body}</span>
              {/if}
              <span class="block text-[11px] text-muted-foreground/70">{timeAgo(n.created_at)}</span>
            </span>
          </button>
        {/each}
      {/if}
    </div>
  </div>
</details>
