<script lang="ts">
  // TODO: Redirect to Keycloak OIDC login
  function handleLogin() {
    window.location.href = '/api/auth/login';
  }
</script>

<div class="flex min-h-[60vh] items-center justify-center">
  <div class="w-full max-w-md rounded-lg border bg-white p-8 shadow-sm">
    <h1 class="mb-6 text-center text-2xl font-bold">Hopper</h1>
    <p class="mb-6 text-center text-gray-600">GPU Cloud Platform for Universities</p>
    <button
      onclick={handleLogin}
      class="w-full rounded-lg bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700"
    >
      Sign in with University SSO
    </button>
  </div>
</div>
