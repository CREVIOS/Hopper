import { get, writable } from 'svelte/store';
import { api } from '$lib/api/client';
import type { AppNotification, NotificationListResponse } from '$lib/types';

export const notificationItems = writable<AppNotification[]>([]);
export const notificationUnreadCount = writable(0);

function sortRecent(items: AppNotification[]) {
  return [...items].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
}

export function setNotifications(response: NotificationListResponse) {
  notificationItems.set(sortRecent(response.notifications));
  notificationUnreadCount.set(response.unread_count);
}

export function pushNotification(notification: AppNotification) {
  const existing = get(notificationItems).some((item) => item.id === notification.id);
  notificationItems.update((items) =>
    sortRecent([notification, ...items.filter((item) => item.id !== notification.id)]).slice(0, 100)
  );
  if (!existing && !notification.read_at) {
    notificationUnreadCount.update((count) => count + 1);
  }
}

export async function refreshNotifications() {
  const response = await api.get<NotificationListResponse>('/notifications');
  setNotifications(response);
}

export async function markNotificationRead(id: string) {
  const updated = await api.post<AppNotification>(`/notifications/${id}/read`);
  notificationItems.update((items) =>
    items.map((item) => (item.id === updated.id ? updated : item))
  );
  notificationUnreadCount.set(
    get(notificationItems).filter((item) => !item.read_at).length
  );
  return updated;
}
