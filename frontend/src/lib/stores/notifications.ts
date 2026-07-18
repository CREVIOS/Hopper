/**
 * Notification store: rolling list + unread count + live SSE stream.
 *
 * connect() opens an EventSource on /api/notifications/stream. Each push is
 * prepended to the list and surfaced as a toast. The server replays nothing
 * on reconnect, so the list is re-fetched on every `connected` event to pick
 * up anything missed while the tab was asleep or the stream was down.
 */
import { writable } from 'svelte/store';
import { toast } from 'svelte-sonner';
import { goto } from '$app/navigation';
import { api } from '$lib/api/client';
import type { AppNotification } from '$lib/types';

export const notifications = writable<AppNotification[]>([]);
export const unreadCount = writable(0);

let source: EventSource | null = null;

interface ListResponse {
  notifications: AppNotification[];
  unread_count: number;
}

export async function loadNotifications(): Promise<void> {
  try {
    const res = await api.get<ListResponse>('/notifications/');
    notifications.set(res.notifications);
    unreadCount.set(res.unread_count);
  } catch {
    // Non-fatal — the bell just stays empty until the next successful load.
  }
}

function showToast(n: AppNotification) {
  const opts: Record<string, unknown> = { description: n.body };
  if (n.data?.action === 'open_vscode' && typeof n.data?.pod_id === 'string') {
    const podId = n.data.pod_id;
    opts.action = { label: 'Open VS Code', onClick: () => goto(`/pods/${podId}`) };
  }
  switch (n.type) {
    case 'success':
      toast.success(n.title, opts);
      break;
    case 'warning':
      toast.warning(n.title, opts);
      break;
    case 'error':
      toast.error(n.title, opts);
      break;
    default:
      toast.info(n.title, opts);
  }
}

export function connectNotifications(): void {
  if (source) return; // already connected (layout re-mounts, HMR)

  source = new EventSource('/api/notifications/stream');

  source.addEventListener('connected', () => {
    // Fresh connection — resync whatever we missed while disconnected.
    void loadNotifications();
  });

  source.addEventListener('notification', (event) => {
    let n: AppNotification;
    try {
      n = JSON.parse((event as MessageEvent).data);
    } catch {
      return;
    }
    notifications.update((items) => [n, ...items].slice(0, 100));
    unreadCount.update((c) => c + 1);
    showToast(n);
  });
  // Transient errors: the browser reconnects automatically, and the
  // `connected` handler resyncs state. Nothing to do here.
}

export function disconnectNotifications(): void {
  source?.close();
  source = null;
}

export async function markRead(id: string): Promise<void> {
  let wasUnread = false;
  notifications.update((items) =>
    items.map((n) => {
      if (n.id === id && !n.read) {
        wasUnread = true;
        return { ...n, read: true };
      }
      return n;
    })
  );
  if (!wasUnread) return;
  unreadCount.update((c) => Math.max(0, c - 1));
  try {
    await api.post(`/notifications/${id}/read`);
  } catch {
    // Optimistic update stands; the server count self-corrects on next load.
  }
}

export async function markAllRead(): Promise<void> {
  notifications.update((items) => items.map((n) => ({ ...n, read: true })));
  unreadCount.set(0);
  try {
    await api.post('/notifications/read-all');
  } catch {
    // Same as above.
  }
}
