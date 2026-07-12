<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { Bell, Circle, ExternalLink } from 'lucide-svelte';
  import { toast } from 'svelte-sonner';
  import { DropdownMenu } from '$lib/ui';
  import type { AppNotification } from '$lib/types';
  import {
    markNotificationRead,
    notificationItems,
    notificationUnreadCount,
    pushNotification,
    refreshNotifications
  } from '$lib/stores/notifications';

  let source: EventSource | null = null;

  const severityToast = {
    success: toast.success,
    warning: toast.warning,
    error: toast.error,
    info: toast.info
  };

  function showToast(notification: AppNotification) {
    const notify = severityToast[notification.severity] ?? toast;
    notify(notification.title, {
      description: notification.body,
      action: notification.action_url
        ? {
            label: 'Open',
            onClick: () => goto(notification.action_url || '/')
          }
        : undefined
    });
  }

  async function openNotification(notification: AppNotification) {
    if (!notification.read_at) {
      await markNotificationRead(notification.id);
    }
    if (notification.action_url) {
      await goto(notification.action_url);
    }
  }

  function formatTime(value: string) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    }).format(date);
  }

  onMount(() => {
    refreshNotifications().catch(() => {});
    source = new EventSource('/api/notifications/stream');
    source.addEventListener('notification', (event) => {
      const notification = JSON.parse((event as MessageEvent).data) as AppNotification;
      pushNotification(notification);
      showToast(notification);
    });
    return () => source?.close();
  });
</script>

<DropdownMenu.Root>
  <DropdownMenu.Trigger>
    {#snippet child({ props })}
      <button
        {...props}
        class="relative inline-flex size-9 items-center justify-center rounded-md transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="Notifications"
      >
        <Bell class="size-4" />
        {#if $notificationUnreadCount > 0}
          <span
            class="absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-4 text-destructive-foreground"
          >
            {$notificationUnreadCount > 9 ? '9+' : $notificationUnreadCount}
          </span>
        {/if}
      </button>
    {/snippet}
  </DropdownMenu.Trigger>

  <DropdownMenu.Content class="w-96 max-w-[calc(100vw-1rem)] p-0">
    <div class="flex items-center justify-between border-b border-border px-3 py-2.5">
      <div>
        <div class="text-sm font-semibold text-foreground">Notifications</div>
        <div class="text-xs text-muted-foreground">Recent activity and alerts</div>
      </div>
      {#if $notificationUnreadCount > 0}
        <span class="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
          {$notificationUnreadCount} unread
        </span>
      {/if}
    </div>

    <div class="max-h-96 overflow-y-auto p-1">
      {#if $notificationItems.length === 0}
        <div class="px-4 py-8 text-center text-sm text-muted-foreground">
          No notifications yet
        </div>
      {:else}
        {#each $notificationItems.slice(0, 10) as notification (notification.id)}
          <button
            class="flex w-full gap-2 rounded-sm px-2 py-2.5 text-left transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onclick={() => openNotification(notification)}
          >
            <span class="mt-1.5 flex size-3 shrink-0 items-center justify-center">
              {#if !notification.read_at}
                <Circle class="size-2 fill-primary text-primary" />
              {/if}
            </span>
            <span class="min-w-0 flex-1">
              <span class="flex items-start justify-between gap-2">
                <span class="truncate text-sm font-medium text-foreground">
                  {notification.title}
                </span>
                {#if notification.action_url}
                  <ExternalLink class="mt-0.5 size-3 shrink-0 text-muted-foreground" />
                {/if}
              </span>
              <span class="mt-0.5 line-clamp-2 text-xs leading-5 text-muted-foreground">
                {notification.body}
              </span>
              <span class="mt-1 block text-[11px] text-muted-foreground">
                {formatTime(notification.created_at)}
              </span>
            </span>
          </button>
        {/each}
      {/if}
    </div>
  </DropdownMenu.Content>
</DropdownMenu.Root>
