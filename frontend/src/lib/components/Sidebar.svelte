<script lang="ts">
  import {
    LayoutDashboard,
    Server,
    CreditCard,
    KeyRound,
    Shield,
    Sparkles
  } from 'lucide-svelte';
  import { page } from '$app/state';
  import type { User } from '$lib/types';
  import { cn } from '$lib/utils';

  let {
    user,
    onNavigate
  }: { user: User | null; onNavigate?: () => void } = $props();

  type NavItem = {
    href: string;
    label: string;
    icon: typeof LayoutDashboard;
    role?: 'admin' | 'professor';
  };

  const items: NavItem[] = [
    { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/pods', label: 'Virtual Machines', icon: Server },
    { href: '/credits', label: 'Credits', icon: CreditCard },
    { href: '/settings/ssh-keys', label: 'SSH Keys', icon: KeyRound }
  ];

  const adminItems: NavItem[] = [
    { href: '/admin', label: 'Admin', icon: Shield }
  ];

  const isAdmin = $derived(user?.role === 'admin' || user?.role === 'professor');

  function isActive(href: string): boolean {
    return page.url.pathname === href || page.url.pathname.startsWith(href + '/');
  }
</script>

<aside
  class="flex h-full w-full flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground"
>
  <div class="flex h-14 items-center gap-2 border-b border-sidebar-border px-5">
    <a href="/dashboard" class="flex items-center gap-2" onclick={onNavigate}>
      <div
        class="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-info text-primary-foreground shadow-md"
      >
        <Sparkles class="size-4" />
      </div>
      <span class="text-lg font-bold tracking-tight">Hopper</span>
    </a>
  </div>

  <nav class="flex-1 space-y-6 overflow-y-auto px-3 py-4">
    <div>
      <div class="px-2 pb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        Workspace
      </div>
      <ul class="space-y-1">
        {#each items as item (item.href)}
          <li>
            <a
              href={item.href}
              onclick={onNavigate}
              class={cn(
                'group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors',
                isActive(item.href)
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-sidebar-muted hover:text-foreground'
              )}
            >
              <item.icon class="size-4 shrink-0" />
              <span>{item.label}</span>
            </a>
          </li>
        {/each}
      </ul>
    </div>

    {#if isAdmin}
      <div>
        <div class="px-2 pb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Manage
        </div>
        <ul class="space-y-1">
          {#each adminItems as item (item.href)}
            <li>
              <a
                href={item.href}
                onclick={onNavigate}
                class={cn(
                  'group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors',
                  isActive(item.href)
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:bg-sidebar-muted hover:text-foreground'
                )}
              >
                <item.icon class="size-4 shrink-0" />
                <span>{item.label}</span>
              </a>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  </nav>

  <div class="border-t border-sidebar-border p-4 text-xs text-muted-foreground">
    <div class="flex items-center gap-1.5">
      <span class="size-2 rounded-full bg-success animate-pulse"></span>
      <span>Cluster online</span>
    </div>
    <p class="mt-1 text-[11px] opacity-70">
      Self-hosted on Kubernetes
    </p>
  </div>
</aside>
