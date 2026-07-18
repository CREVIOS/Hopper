<script lang="ts">
  import { KeyRound, AlertCircle, Check, Mail, Lock, Eye, EyeOff } from 'lucide-svelte';
  import { Button } from '$lib/ui';
  import AuthLayout from '$lib/auth/AuthLayout.svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { api, ApiError } from '$lib/api/client';
  import PasswordRequirements from '$lib/auth/PasswordRequirements.svelte';
  import { explainFailures, unmetRules } from '$lib/auth/passwordPolicy';

  // 'request' asks for the email; 'reset' collects the code + new password.
  let step = $state<'request' | 'reset'>('request');
  let email = $state('');
  let code = $state('');
  let password = $state('');
  let showPw = $state(false);
  let submitting = $state(false);
  let error = $state<string | null>(null);
  let resent = $state(false);
  let passwordRejected = $state(false);

  async function requestCode(e: SubmitEvent) {
    e.preventDefault();
    error = null;
    submitting = true;
    try {
      // Always 200 (no user enumeration); advance regardless.
      await api.post('/auth/forgot-password', { email });
      step = 'reset';
    } catch (err) {
      error = err instanceof ApiError ? err.message : 'Something went wrong. Please try again.';
    } finally {
      submitting = false;
    }
  }

  async function reset(e: SubmitEvent) {
    e.preventDefault();
    error = null;
    const unmet = unmetRules(password, email);
    if (unmet.length > 0) {
      error = explainFailures(unmet);
      passwordRejected = true;
      return;
    }
    passwordRejected = false;
    submitting = true;
    try {
      await api.post('/auth/reset-password', { email, code, password });
      window.location.href = '/login?reset=1';
    } catch (err) {
      error = err instanceof ApiError ? err.message : 'Reset failed. Please try again.';
      passwordRejected =
        err instanceof ApiError && err.status === 400 && /password/i.test(err.message);
      submitting = false;
    }
  }

  async function resend() {
    error = null;
    resent = false;
    try {
      await api.post('/auth/forgot-password', { email });
      resent = true;
    } catch {
      error = 'Could not resend the code. Please try again.';
    }
  }
</script>

<AuthLayout>
  <div
    class="w-full max-w-[420px] rounded-3xl border border-white bg-white/95 p-8 shadow-2xl shadow-indigo-950/10 backdrop-blur-sm dark:border-white/10 dark:bg-slate-900/90 sm:p-9"
  >
    <div class="flex flex-col items-center gap-4 text-center">
      <div
        class="grid size-14 place-items-center rounded-2xl bg-white shadow-md ring-1 ring-slate-100 dark:bg-slate-800 dark:ring-white/10"
      >
        <KeyRound class="size-6 text-slate-900 dark:text-white" strokeWidth={2} />
      </div>
      <div class="space-y-1.5">
        <h1 class="text-[1.6rem] font-bold leading-tight tracking-tight">Reset your password</h1>
        <p class="text-sm text-muted-foreground">
          {#if step === 'request'}
            Enter your account email and we'll send a secure reset code.
          {:else}
            Enter the code sent to <span class="font-medium text-foreground">{email}</span> and choose a new password.
          {/if}
        </p>
      </div>
    </div>

    {#if error}
      <div
        class="mt-6 flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
      >
        <AlertCircle class="mt-0.5 size-4 shrink-0" />
        <span>{error}</span>
      </div>
    {/if}

    {#if step === 'request'}
      <form onsubmit={requestCode} class="mt-6 space-y-4">
        <div class="relative">
          <Mail class="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="email"
            bind:value={email}
            required
            autocomplete="email"
            placeholder="Email"
            class="h-11 w-full rounded-xl border border-input bg-secondary/60 pl-10 pr-3 text-sm outline-none ring-ring/50 transition focus:border-ring focus:bg-background focus:ring-2 dark:bg-secondary/40"
          />
        </div>
        <Button type="submit" disabled={submitting} class="h-11 w-full rounded-xl text-[15px] font-semibold">
          {#if submitting}<Spinner class="size-4" /> Sending…{:else}Send reset code{/if}
        </Button>
      </form>
    {:else}
      <form onsubmit={reset} class="mt-6 space-y-4">
        <input
          bind:value={code}
          required
          inputmode="numeric"
          autocomplete="one-time-code"
          placeholder="000000"
          class="h-14 w-full rounded-xl border border-input bg-secondary/60 text-center text-2xl font-bold tracking-[0.5em] outline-none ring-ring/50 transition focus:border-ring focus:bg-background focus:ring-2 dark:bg-secondary/40"
        />
        <div>
          <div class="relative">
            <Lock class="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type={showPw ? 'text' : 'password'}
              bind:value={password}
              required
              autocomplete="new-password"
              placeholder="New password"
              aria-describedby="fp-password-reqs"
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
          <div id="fp-password-reqs">
            <PasswordRequirements {password} username={email} showErrors={passwordRejected} />
          </div>
        </div>
        <Button type="submit" disabled={submitting} class="h-11 w-full rounded-xl text-[15px] font-semibold">
          {#if submitting}<Spinner class="size-4" /> Resetting…{:else}Reset password{/if}
        </Button>
        <div class="flex items-center justify-between text-sm">
          <button type="button" onclick={() => { step = 'request'; error = null; }} class="text-muted-foreground hover:underline">← Back</button>
          <button type="button" onclick={resend} class="font-medium text-primary hover:underline">Resend code</button>
        </div>
        {#if resent}
          <p class="flex items-center gap-1.5 text-xs text-muted-foreground"><Check class="size-3.5" /> A new code is on its way.</p>
        {/if}
      </form>
    {/if}

    <p class="mt-6 text-center text-sm text-muted-foreground">
      <a href="/login" data-sveltekit-reload class="font-semibold text-primary hover:underline">Back to sign in</a>
    </p>
  </div>
</AuthLayout>
