<script lang="ts">
  import {
    LayoutDashboard,
    Server,
    Sparkles,
    Bot,
    CreditCard,
    KeyRound,
    Bell,
    Shield,
    GraduationCap,
    PanelLeftClose,
    PanelLeftOpen
  } from 'lucide-svelte';
  import { page } from '$app/state';
  import type { User } from '$lib/types';
  import { cn } from '$lib/utils';
  import HopperLogo from '$lib/brand/HopperLogo.svelte';

  let {
    user,
    onNavigate,
    collapsed = false,
    onToggleCollapse
  }: {
    user: User | null;
    onNavigate?: () => void;
    /** Render the icon-only rail (desktop only). */
    collapsed?: boolean;
    /** When provided, shows the collapse/expand toggle in the header. */
    onToggleCollapse?: () => void;
  } = $props();

  type NavItem = {
    href: string;
    label: string;
    icon: typeof LayoutDashboard;
    role?: 'admin' | 'professor';
  };

  const items: NavItem[] = [
    { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/pods', label: 'Virtual Machines', icon: Server },
    { href: '/sandbox', label: 'Smart Sandbox', icon: Sparkles },
    { href: '/agents', label: 'AI Agents', icon: Bot },
    { href: '/credits', label: 'Credits', icon: CreditCard },
    { href: '/settings/ssh-keys', label: 'SSH Keys', icon: KeyRound },
    { href: '/settings/notifications', label: 'Notifications', icon: Bell }
  ];

  const adminItems: NavItem[] = [
    { href: '/admin', label: 'Admin', icon: Shield },
    { href: '/teacher', label: 'Teaching', icon: GraduationCap, role: 'professor' }
  ];

  const isAdmin = $derived(user?.role === 'admin' || user?.role === 'professor');
  // Per-item gating: an item with no `role` shows for any manager; a role-bound
  // item (e.g. Teaching → professor) shows only to that role.
  const visibleAdminItems = $derived(
    adminItems.filter((i) => !i.role || i.role === user?.role)
  );

  function isActive(href: string): boolean {
    return page.url.pathname === href || page.url.pathname.startsWith(href + '/');
  }
</script>

<aside
  class="flex h-full w-full flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground"
>
  <div
    class={cn(
      'flex h-14 items-center border-b border-sidebar-border',
      collapsed ? 'justify-center px-2' : 'gap-2 px-5'
    )}
  >
    {#if collapsed}
      <!-- Collapsed: the brand mark doubles as the expand toggle. -->
      <button
        type="button"
        onclick={onToggleCollapse}
        title="Expand sidebar"
        aria-label="Expand sidebar"
        class="group relative flex size-9 items-center justify-center rounded-lg transition-colors hover:bg-sidebar-muted"
      >
        <HopperLogo size={28} class="transition-opacity group-hover:opacity-0" />
        <PanelLeftOpen
          class="absolute size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
        />
      </button>
    {:else}
      <a href="/dashboard" class="group/brand flex min-w-0 items-center gap-2" onclick={onNavigate}>
        <HopperLogo size={28} />
        <span class="truncate text-lg font-bold tracking-tight">Hopper</span>
      </a>
      {#if onToggleCollapse}
        <button
          type="button"
          onclick={onToggleCollapse}
          title="Collapse sidebar"
          aria-label="Collapse sidebar"
          class="ml-auto flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-sidebar-muted hover:text-foreground"
        >
          <PanelLeftClose class="size-4" />
        </button>
      {/if}
    {/if}
  </div>

  <nav class={cn('flex-1 space-y-6 overflow-y-auto py-4', collapsed ? 'px-2' : 'px-3')}>
    <div>
      {#if collapsed}
        <div class="mx-2 mb-2 h-px bg-sidebar-border"></div>
      {:else}
        <div class="px-2 pb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Workspace
        </div>
      {/if}
      <ul class="space-y-1">
        {#each items as item (item.href)}
          <li>
            <a
              href={item.href}
              onclick={onNavigate}
              title={collapsed ? item.label : undefined}
              class={cn(
                'group flex items-center rounded-md text-sm font-medium transition-colors',
                collapsed ? 'justify-center p-2.5' : 'gap-2.5 px-2.5 py-2',
                isActive(item.href)
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-sidebar-muted hover:text-foreground'
              )}
            >
              <item.icon
                class={cn(
                  'size-4 shrink-0 transition-transform duration-200 group-hover:scale-110',
                  isActive(item.href) && 'scale-110'
                )}
              />
              {#if !collapsed}<span class="truncate">{item.label}</span>{/if}
            </a>
          </li>
        {/each}
      </ul>
    </div>

    {#if isAdmin}
      <div>
        {#if collapsed}
          <div class="mx-2 mb-2 h-px bg-sidebar-border"></div>
        {:else}
          <div class="px-2 pb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Manage
          </div>
        {/if}
        <ul class="space-y-1">
          {#each visibleAdminItems as item (item.href)}
            <li>
              <a
                href={item.href}
                onclick={onNavigate}
                title={collapsed ? item.label : undefined}
                class={cn(
                  'group flex items-center rounded-md text-sm font-medium transition-colors',
                  collapsed ? 'justify-center p-2.5' : 'gap-2.5 px-2.5 py-2',
                  isActive(item.href)
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:bg-sidebar-muted hover:text-foreground'
                )}
              >
                <item.icon
                class={cn(
                  'size-4 shrink-0 transition-transform duration-200 group-hover:scale-110',
                  isActive(item.href) && 'scale-110'
                )}
              />
                {#if !collapsed}<span class="truncate">{item.label}</span>{/if}
              </a>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  </nav>

  {#if collapsed}
    <div
      class="flex items-center justify-center border-t border-sidebar-border p-4"
      title="Cluster online · Self-hosted on Kubernetes"
    >
      <span class="size-2 animate-pulse rounded-full bg-success"></span>
    </div>
  {:else}
    <div class="border-t border-sidebar-border p-4 text-xs text-muted-foreground">
      <div class="flex items-center gap-1.5">
        <span class="size-2 animate-pulse rounded-full bg-success"></span>
        <span>Cluster online</span>
      </div>
      <p class="mt-1 text-[11px] opacity-70">Self-hosted on Kubernetes</p>
    </div>
  {/if}
</aside>
