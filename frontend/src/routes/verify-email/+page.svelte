<script lang="ts">
  import { AlertCircle, Check, MailCheck, Mail } from 'lucide-svelte';
  import { page } from '$app/state';
  import { Button } from '$lib/ui';
  import AuthLayout from '$lib/auth/AuthLayout.svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { api, ApiError } from '$lib/api/client';

  let email = $state(page.url.searchParams.get('email') ?? '');
  let code = $state('');
  let submitting = $state(false);
  let error = $state<string | null>(null);
  let resent = $state(false);

  async function verify(e: SubmitEvent) {
    e.preventDefault();
    error = null;
    submitting = true;
    try {
      await api.post('/auth/verify-email', { email, code });
      window.location.href = '/login?verified=1';
    } catch (err) {
      error = err instanceof ApiError ? err.message : 'Verification failed. Please try again.';
      submitting = false;
    }
  }

  async function resend() {
    error = null;
    resent = false;
    try {
      await api.post('/auth/resend-code', { email, purpose: 'verify_email' });
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
        <MailCheck class="size-6 text-slate-900 dark:text-white" strokeWidth={2} />
      </div>
      <div class="space-y-1.5">
        <h1 class="text-[1.6rem] font-bold leading-tight tracking-tight">Verify your email</h1>
        <p class="text-sm text-muted-foreground">
          Enter the 6-digit code we emailed you to activate your account.
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

    <form onsubmit={verify} class="mt-6 space-y-4">
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
      <input
        bind:value={code}
        required
        inputmode="numeric"
        autocomplete="one-time-code"
        placeholder="000000"
        class="h-14 w-full rounded-xl border border-input bg-secondary/60 text-center text-2xl font-bold tracking-[0.5em] outline-none ring-ring/50 transition focus:border-ring focus:bg-background focus:ring-2 dark:bg-secondary/40"
      />
      <Button type="submit" disabled={submitting} class="h-11 w-full rounded-xl text-[15px] font-semibold">
        {#if submitting}<Spinner class="size-4" /> Verifying…{:else}Verify email{/if}
      </Button>
    </form>

    <div class="mt-5 flex items-center justify-between text-sm">
      <a href="/login" data-sveltekit-reload class="text-muted-foreground hover:underline">← Back to sign in</a>
      <button type="button" onclick={resend} class="font-medium text-primary hover:underline">Resend code</button>
    </div>
    {#if resent}
      <p class="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground"><Check class="size-3.5" /> A new code is on its way.</p>
    {/if}
  </div>
</AuthLayout>
