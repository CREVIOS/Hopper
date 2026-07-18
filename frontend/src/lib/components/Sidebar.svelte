<script lang="ts">
  import {
    LayoutDashboard,
    Server,
    ListOrdered,
    CreditCard,
    KeyRound,
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

  const sections: { label: string; items: NavItem[] }[] = [
    {
      label: 'Platform',
      items: [
        { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
        { href: '/pods', label: 'Virtual Machines', icon: Server },
        { href: '/pods/queue', label: 'Queue', icon: ListOrdered }
      ]
    },
    { label: 'Billing', items: [{ href: '/credits', label: 'Credits', icon: CreditCard }] },
    { label: 'Account', items: [{ href: '/settings/ssh-keys', label: 'SSH Keys', icon: KeyRound }] }
  ];

  const adminItems: NavItem[] = [
    { href: '/admin', label: 'Admin', icon: Shield, role: 'admin' },
    { href: '/teacher', label: 'Teaching', icon: GraduationCap, role: 'professor' }
  ];

  const isAdmin = $derived(user?.role === 'admin' || user?.role === 'professor');
  // Per-item gating: an item with no `role` shows for any manager; a role-bound
  // item shows only to that role — Admin → admin, Teaching → professor. Teachers
  // therefore see only the Teaching console, never the admin panel.
  const visibleAdminItems = $derived(
    adminItems.filter((i) => !i.role || i.role === user?.role)
  );

  // Initials for the footer avatar — first letters of up to two name parts.
  const initials = $derived(
    (user?.name ?? user?.email ?? 'U')
      .split(/[\s@.]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0])
      .join('')
      .toUpperCase()
  );

  function isActive(href: string): boolean {
    const path = page.url.pathname;
    // "Virtual Machines" (/pods) still lights up on VM detail pages (/pods/{id})
    // but NOT on the /pods/queue sub-page, which has its own nav entry.
    if (href === '/pods') {
      return (
        (path === '/pods' || path.startsWith('/pods/')) &&
        !path.startsWith('/pods/queue')
      );
    }
    return path === href || path.startsWith(href + '/');
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
      <a href="/dashboard" class="group/brand flex min-w-0 items-center gap-2.5" onclick={onNavigate}>
        <HopperLogo size={30} />
        <div class="flex min-w-0 flex-col leading-none">
          <span class="truncate text-[15px] font-bold tracking-tight">Hopper</span>
          <span class="mt-1 truncate text-[11px] font-medium text-muted-foreground">Cloud VM Platform</span>
        </div>
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

  {#snippet navLink(item: NavItem)}
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
  {/snippet}

  {#snippet navGroup(label: string, groupItems: NavItem[])}
    <div>
      {#if collapsed}
        <div class="mx-2 mb-2 h-px bg-sidebar-border"></div>
      {:else}
        <div class="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
      {/if}
      <ul class="space-y-1">
        {#each groupItems as item (item.href)}
          {@render navLink(item)}
        {/each}
      </ul>
    </div>
  {/snippet}

  <nav class={cn('flex-1 space-y-5 overflow-y-auto py-4', collapsed ? 'px-2' : 'px-3')}>
    {#each sections as sec (sec.label)}
      {@render navGroup(sec.label, sec.items)}
    {/each}
    {#if isAdmin && visibleAdminItems.length}
      {@render navGroup('Administration', visibleAdminItems)}
    {/if}
  </nav>

  {#if collapsed}
    <div class="flex items-center justify-center border-t border-sidebar-border p-3" title={user?.name ?? 'User'}>
      <span class="relative grid size-9 place-items-center rounded-full bg-muted text-sm font-semibold text-foreground">
        {initials}
        <span class="absolute -bottom-0.5 -right-0.5 size-2.5 animate-pulse rounded-full border-2 border-sidebar bg-success"></span>
      </span>
    </div>
  {:else}
    <div class="border-t border-sidebar-border p-3">
      <div class="flex items-center gap-2.5 rounded-lg p-2">
        <span class="relative grid size-9 shrink-0 place-items-center rounded-full bg-muted text-sm font-semibold text-foreground">
          {initials}
          <span class="absolute -bottom-0.5 -right-0.5 size-2.5 animate-pulse rounded-full border-2 border-sidebar bg-success"></span>
        </span>
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-medium text-foreground">{user?.name ?? 'User'}</p>
          <p class="truncate text-[11px] text-muted-foreground">{user?.email ?? 'Cluster online'}</p>
        </div>
      </div>
    </div>
  {/if}
</aside>
