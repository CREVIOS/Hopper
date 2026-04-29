<script lang="ts">
  import '../app.css';
  import type { Snippet } from 'svelte';
  import type { User } from '$lib/types';
  import { ModeWatcher } from 'mode-watcher';
  import { Menu, X } from 'lucide-svelte';
  import { page } from '$app/state';
  import { Toaster, Button } from '$lib/ui';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import UserMenu from '$lib/components/UserMenu.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import CreditBadge from '$lib/components/CreditBadge.svelte';
  import ConfirmHost from '$lib/components/ConfirmHost.svelte';

  let {
    data,
    children
  }: {
    data: { isAuthenticated: boolean; user: User | null; balance?: number };
    children: Snippet;
  } = $props();

  let mobileOpen = $state(false);

  // Close the mobile sidebar on navigation.
  $effect(() => {
    page.url.pathname; // track
    mobileOpen = false;
  });

  const isLogin = $derived(page.url.pathname === '/login');
</script>

<ModeWatcher defaultMode="system" />
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
    <div class="hidden w-64 shrink-0 lg:block">
      <div class="fixed inset-y-0 w-64">
        <Sidebar user={data.user} />
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
        class="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-border bg-background/80 px-4 backdrop-blur-md sm:px-6"
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
          <div class="text-sm font-medium text-muted-foreground">
            <a href="/dashboard" class="lg:hidden font-bold text-foreground">Hopper</a>
          </div>
        </div>
        <div class="flex items-center gap-2 sm:gap-3">
          {#if typeof data.balance === 'number'}
            <CreditBadge balance={data.balance} class="hidden sm:inline-flex" />
          {/if}
          <ThemeToggle />
          {#if data.user}
            <UserMenu user={data.user} />
          {/if}
        </div>
      </header>

      <main class="flex-1 overflow-x-hidden">
        <div class="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {@render children()}
        </div>
      </main>
    </div>
  </div>
{/if}
