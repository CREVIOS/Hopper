<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import type { Snippet } from 'svelte';
  import type { User } from '$lib/types';
  import { ModeWatcher } from 'mode-watcher';
  import { Menu, X } from 'lucide-svelte';
  import { page, navigating } from '$app/state';
  import { Toaster, Button } from '$lib/ui';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import HopperLogo from '$lib/brand/HopperLogo.svelte';
  import UserMenu from '$lib/components/UserMenu.svelte';
  import NotificationBell from '$lib/components/NotificationBell.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import CreditBadge from '$lib/components/CreditBadge.svelte';
  import ConfirmHost from '$lib/components/ConfirmHost.svelte';
  import DashboardSkeleton from '$lib/components/DashboardSkeleton.svelte';

  let {
    data,
    children
  }: {
    data: { isAuthenticated: boolean; user: User | null; balance?: number };
    children: Snippet;
  } = $props();

  let mobileOpen = $state(false);
  let liveBalance = $state<number | null>(typeof data.balance === 'number' ? data.balance : null);

  // Desktop sidebar collapse — persisted so it survives reloads.
  let collapsed = $state(false);
  const COLLAPSE_KEY = 'hopper:sidebar-collapsed';

  onMount(() => {
    collapsed = localStorage.getItem(COLLAPSE_KEY) === '1';

    // Keepalive: the access token (session_token cookie) lives ~5 min. Long-lived
    // pages with no navigation — chiefly the pod terminal's WebSocket — would
    // otherwise let it expire, so a transient WS drop reconnects with a dead
    // cookie (close 1008) and never recovers. Refresh it well before expiry so
    // the cookie stays valid for reconnects and client /api calls alike.
    if (!data.isAuthenticated) return;
    const refreshTimer = setInterval(() => {
      fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
    }, 4 * 60 * 1000);
    const balanceTimer = setInterval(async () => {
      try {
        const res = await fetch('/api/credits/balance', { credentials: 'same-origin' });
        if (!res.ok) return;
        const json = await res.json();
        if (typeof json?.balance === 'number') {
          liveBalance = json.balance;
        }
      } catch {}
    }, 5000);
    return () => {
      clearInterval(refreshTimer);
      clearInterval(balanceTimer);
    };
  });

  $effect(() => {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
    }
  });

  // Close the mobile sidebar on navigation.
  $effect(() => {
    page.url.pathname; // track
    mobileOpen = false;
  });

  const isLogin = $derived(page.url.pathname === '/login');
  const loadingSkeleton = $derived.by(() => {
    if (!data.isAuthenticated) return null;

    const pathname = navigating.to?.url.pathname;
    if (!pathname) return null;
    if (pathname === '/dashboard') return 'dashboard';
    if (pathname === '/admin') return 'admin';
    if (pathname === '/teacher') return 'teacher';
    if (pathname === '/credits') return 'credits';
    return null;
  });

  // One source of truth for document titles — pages don't set their own.
  const TITLES: [RegExp, string][] = [
    [/^\/dashboard/, 'Dashboard'],
    [/^\/pods\/queue/, 'Queue'],
    [/^\/pods\/[^/]+/, 'VM Detail'],
    [/^\/pods/, 'Virtual Machines'],
    [/^\/credits/, 'Credits'],
    [/^\/admin/, 'Admin'],
    [/^\/teacher/, 'Teaching'],
    [/^\/settings\/ssh-keys/, 'SSH Keys'],
    [/^\/login/, 'Sign in'],
    [/^\/signup/, 'Sign up'],
    [/^\/forgot-password/, 'Reset password'],
    [/^\/verify-email/, 'Verify email']
  ];
  const pageTitle = $derived.by(() => {
    const hit = TITLES.find(([re]) => re.test(page.url.pathname));
    return hit ? `${hit[1]} · Hopper` : 'Hopper — Cloud VMs for students & teams';
  });
</script>

<svelte:head>
  <title>{pageTitle}</title>
</svelte:head>

<ModeWatcher defaultMode="light" />
<Toaster />
<ConfirmHost />

{#if !data.isAuthenticated || isLogin}
  <!-- Public layout: login & redirects -->
  <div class="min-h-screen bg-background text-foreground">
    {@render children()}
  </div>
{:else}
  <!-- Authenticated layout: sidebar + topbar -->
  <div class="flex min-h-screen bg-background text-foreground">
    <!-- Desktop sidebar -->
    <div
      class={`hidden shrink-0 transition-[width] duration-200 ease-out lg:block ${collapsed ? 'w-16' : 'w-64'}`}
    >
      <div
        class={`fixed inset-y-0 transition-[width] duration-200 ease-out ${collapsed ? 'w-16' : 'w-64'}`}
      >
        <Sidebar
          user={data.user}
          {collapsed}
          onToggleCollapse={() => (collapsed = !collapsed)}
        />
      </div>
    </div>

    <!-- Mobile sidebar overlay -->
    {#if mobileOpen}
      <div
        class="fixed inset-0 z-40 bg-black/60 lg:hidden"
        onclick={() => (mobileOpen = false)}
        role="presentation"
      ></div>
      <div class="fixed inset-y-0 left-0 z-50 w-64 lg:hidden">
        <Sidebar user={data.user} onNavigate={() => (mobileOpen = false)} />
      </div>
    {/if}

    <div class="flex min-w-0 flex-1 flex-col">
      <!-- Topbar -->
      <header
        class="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-sidebar-border bg-sidebar px-4 sm:px-6"
      >
        <div class="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            class="lg:hidden"
            onclick={() => (mobileOpen = !mobileOpen)}
            aria-label="Toggle navigation"
          >
            {#if mobileOpen}
              <X class="size-4" />
            {:else}
              <Menu class="size-4" />
            {/if}
          </Button>
          <a href="/dashboard" class="flex items-center gap-2 lg:hidden">
            <HopperLogo size={24} />
            <span class="font-bold text-foreground">Hopper</span>
          </a>
        </div>
        <div class="flex items-center gap-2 sm:gap-3">
          {#if typeof liveBalance === 'number'}
            <CreditBadge balance={liveBalance} class="hidden sm:inline-flex" />
          {/if}
          <NotificationBell />
          <ThemeToggle />
          {#if data.user}
            <UserMenu user={data.user} />
          {/if}
        </div>
      </header>

      <main class="flex-1 overflow-x-hidden">
        <div class="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {#if loadingSkeleton}
            <DashboardSkeleton variant={loadingSkeleton} />
          {:else}
            {@render children()}
          {/if}
        </div>
      </main>
    </div>
  </div>
{/if}
