<script lang="ts">
  import { goto } from '$app/navigation';
  import { isAuthenticated } from '$lib/stores/auth';
  import { onMount } from 'svelte';

  onMount(() => {
    if ($isAuthenticated) {
      goto('/dashboard');
    } else {
      goto('/login');
    }
  });
</script>

<div class="flex h-64 items-center justify-center">
  <p class="text-gray-500">Redirecting...</p>
</div>
