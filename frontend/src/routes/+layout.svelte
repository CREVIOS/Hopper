<script lang="ts">
  import '../app.css';
  import { user, isAuthenticated } from '$lib/stores/auth';
  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();
</script>

<div class="min-h-screen bg-gray-50">
  <nav class="border-b bg-white px-6 py-3">
    <div class="mx-auto flex max-w-7xl items-center justify-between">
      <a href="/" class="text-xl font-bold">Hopper</a>
      {#if $isAuthenticated}
        <div class="flex items-center gap-4">
          <a href="/dashboard" class="text-sm hover:underline">Dashboard</a>
          <a href="/pods" class="text-sm hover:underline">Pods</a>
          <a href="/credits" class="text-sm hover:underline">Credits</a>
          {#if $user?.role === 'platform_admin' || $user?.role === 'university_admin'}
            <a href="/admin" class="text-sm hover:underline">Admin</a>
          {/if}
          <span class="text-sm text-gray-500">{$user?.email}</span>
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
