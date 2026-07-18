<script lang="ts">
  import {
    LogIn,
    KeyRound,
    ArrowRight,
    AlertCircle,
    Check,
    ShieldCheck,
    Mail,
    Lock,
    Eye,
    EyeOff
  } from 'lucide-svelte';
  import { page } from '$app/state';
  import { dev } from '$app/environment';
  import { Button } from '$lib/ui';
  import AuthLayout from '$lib/auth/AuthLayout.svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { api, ApiError } from '$lib/api/client';

  let signing = $state(false);

  // Themed email + password login (direct grant). SSO button below still works.
  let email = $state('');
  let password = $state('');
  let showPw = $state(false);
  let submitting = $state(false);
  let formError = $state<string | null>(null);
  // When login is blocked because the email isn't verified, offer a verify link.
  let needsVerify = $state(false);

  async function handlePasswordLogin(e: SubmitEvent) {
    e.preventDefault();
    formError = null;
    needsVerify = false;
    submitting = true;
    try {
      await api.post('/auth/login', { email, password });
      window.location.href = '/dashboard';
    } catch (err) {
      if (err instanceof ApiError && /verify your email/i.test(err.message)) {
        needsVerify = true;
      }
      formError =
        err instanceof ApiError && err.status === 401
          ? 'Invalid email or password.'
          : err instanceof ApiError
            ? err.message
            : 'Sign-in failed. Please try again.';
      submitting = false;
    }
  }

  // Surface OAuth error redirects (?error=domain | email_unverified | oidc).
  const errorParam = $derived(page.url.searchParams.get('error'));
  const errorMessage = $derived.by(() => {
    switch (errorParam) {
      case 'domain':
        return 'This account is not permitted to sign in. Contact your department admin if you need access.';
      case 'email_unverified':
        return 'Verify your email address (check your inbox), then sign in again.';
      case 'oidc':
        return 'Sign-in was cancelled or rejected by the identity provider.';
      case 'session_expired':
        return 'Session expired, please log in again.';
      default:
        return null;
    }
  });
  const sessionExpiredMessage = $derived(
    page.url.searchParams.get('session_expired') === '1'
      ? 'Session expired, please log in again.'
      : null
  );
  // Success redirects from the verify / reset flows.
  const successMessage = $derived.by(() => {
    if (page.url.searchParams.get('verified') === '1') return 'Email verified — you can now sign in.';
    if (page.url.searchParams.get('reset') === '1') return 'Password reset — sign in with your new password.';
    return null;
  });

  function handleLogin() {
    signing = true;
    window.location.href = '/api/auth/login';
  }

  // Reset the SSO button on bfcache restore (browser Back after redirect).
  function handlePageShow() {
    signing = false;
  }
</script>

<svelte:window onpageshow={handlePageShow} />

<AuthLayout>
  <div
    class="w-full max-w-[420px] rounded-3xl border border-white bg-white/95 p-8 shadow-2xl shadow-indigo-950/10 backdrop-blur-sm dark:border-white/10 dark:bg-slate-900/90 sm:p-9"
  >
    <div class="flex flex-col items-center gap-4 text-center">
      <div
        class="grid size-14 place-items-center rounded-2xl bg-white shadow-md ring-1 ring-slate-100 dark:bg-slate-800 dark:ring-white/10"
      >
        <LogIn class="size-6 text-slate-900 dark:text-white" strokeWidth={2} />
      </div>
      <div class="space-y-1.5">
        <h1 class="text-[1.6rem] font-bold leading-tight tracking-tight">Sign in with email</h1>
        <p class="text-sm text-muted-foreground">
          Access your Hopper workspace and spin up cloud VMs in seconds.
        </p>
      </div>
    </div>

    {#if errorMessage || formError}
      <div
        class="mt-6 flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
      >
        <AlertCircle class="mt-0.5 size-4 shrink-0" />
        <span>{formError ?? errorMessage}</span>
      </div>
    {:else if successMessage}
      <div
        class="mt-6 flex items-start gap-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-600 dark:text-emerald-400"
      >
        <Check class="mt-0.5 size-4 shrink-0" />
        <span>{successMessage}</span>
      </div>
    {/if}

    {#if sessionExpiredMessage && !errorMessage && !formError}
      <div
        class="mt-6 flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
      >
        <AlertCircle class="mt-0.5 size-4 shrink-0" />
        <span>{sessionExpiredMessage}</span>
      </div>
    {/if}

    <form onsubmit={handlePasswordLogin} class="mt-6 space-y-4">
      <div class="relative">
        <Mail class="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="email"
          bind:value={email}
          required
          autocomplete="email"
          placeholder="University email"
          class="h-11 w-full rounded-xl border border-input bg-secondary/60 pl-10 pr-3 text-sm outline-none ring-ring/50 transition focus:border-ring focus:bg-background focus:ring-2 dark:bg-secondary/40"
        />
      </div>

      <div class="space-y-3">
        <div class="relative">
          <Lock class="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type={showPw ? 'text' : 'password'}
            bind:value={password}
            required
            autocomplete="current-password"
            placeholder="Password"
            class="h-11 w-full rounded-xl border border-input bg-secondary/60 pl-10 pr-10 text-sm outline-none ring-ring/50 transition focus:border-ring focus:bg-background focus:ring-2 dark:bg-secondary/40"
          />
          <button
            type="button"
            onclick={() => (showPw = !showPw)}
            class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground transition hover:text-foreground"
            aria-label={showPw ? 'Hide password' : 'Show password'}
          >
            {#if showPw}<EyeOff class="size-4" />{:else}<Eye class="size-4" />{/if}
          </button>
        </div>

        <div class="flex justify-end">
          <a
            href="/forgot-password"
            class="text-[13px] font-medium text-primary hover:underline"
          >
            Forgot password?
          </a>
        </div>
      </div>

      {#if needsVerify}
        <p class="text-sm text-muted-foreground">
          <a
            href={`/verify-email?email=${encodeURIComponent(email)}`}
            class="font-medium text-foreground underline underline-offset-2"
          >
            Verify your email
          </a>
          to finish setting up your account.
        </p>
      {/if}

      <Button type="submit" disabled={submitting} class="h-11 w-full rounded-xl text-[15px] font-semibold">
        {#if submitting}<Spinner class="size-4" /> Signing in…{:else}Sign in{/if}
      </Button>
    </form>

    <div class="my-5 flex items-center gap-3 text-xs text-muted-foreground">
      <span class="h-px flex-1 bg-border"></span> Or continue with
      <span class="h-px flex-1 bg-border"></span>
    </div>

    <Button
      onclick={handleLogin}
      disabled={signing}
      variant="outline"
      class="group h-11 w-full justify-center gap-2 rounded-xl text-[15px] font-medium"
    >
      <ShieldCheck class="size-4 text-primary" />
      {signing ? 'Redirecting…' : 'University SSO'}
      <ArrowRight class="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </Button>

    {#if dev}
      <!-- Dev-only: mint a session directly (real SSO can't complete on localhost). -->
      <div class="mt-2.5 grid grid-cols-2 gap-2.5">
        <a
          href="/dev-login?as=admin"
          data-sveltekit-reload
          class="flex items-center justify-center gap-2 rounded-xl border border-dashed border-warning/50 bg-warning/5 px-3 py-2 text-sm font-medium text-warning transition-colors hover:bg-warning/10"
        >
          <KeyRound class="size-4" /> Dev: admin
        </a>
        <a
          href="/dev-login?as=user"
          data-sveltekit-reload
          class="flex items-center justify-center gap-2 rounded-xl border border-dashed border-warning/50 bg-warning/5 px-3 py-2 text-sm font-medium text-warning transition-colors hover:bg-warning/10"
        >
          <KeyRound class="size-4" /> Dev: user
        </a>
      </div>
    {/if}

    <p class="mt-6 text-center text-sm text-muted-foreground">
      Don't have an account?
      <a href="/signup" data-sveltekit-reload class="font-semibold text-primary hover:underline">Sign up</a>
    </p>
  </div>
</AuthLayout>
