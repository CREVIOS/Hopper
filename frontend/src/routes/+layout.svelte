<script lang="ts">
  import '../app.css';
  import type { Snippet } from 'svelte';
  import type { User } from '$lib/types';

  let { data, children }: { data: { isAuthenticated: boolean; user: User | null }; children: Snippet } = $props();

  function logout() {
    fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }).then(() => {
      window.location.href = '/login';
    });
  }
</script>

<div class="min-h-screen bg-gray-50">
  <nav class="border-b bg-white px-6 py-3">
    <div class="mx-auto flex max-w-7xl items-center justify-between">
      <a href="/" class="text-xl font-bold">Hopper</a>
      {#if data.isAuthenticated}
        <div class="flex items-center gap-4">
          <a href="/dashboard" class="text-sm hover:underline">Dashboard</a>
          <a href="/pods" class="text-sm hover:underline">VMs</a>
          <a href="/credits" class="text-sm hover:underline">Credits</a>
          {#if data.user?.role === 'admin' || data.user?.role === 'professor'}
            <a href="/admin" class="text-sm hover:underline">Admin</a>
          {/if}
          <span class="text-sm text-gray-500">{data.user?.email}</span>
          <button
            onclick={logout}
            class="rounded bg-gray-200 px-3 py-1 text-sm hover:bg-gray-300"
          >
            Logout
          </button>
        </div>
      {:else}
        <a href="/login" class="text-sm hover:underline">Login</a>
      {/if}
    </div>
  </nav>
  <main class="mx-auto max-w-7xl p-6">
    {@render children()}
  </main>
</div>
