<script lang="ts">
  import { KeyRound, ArrowRight, AlertCircle, Check } from 'lucide-svelte';
  import { Button, Input, Label } from '$lib/ui';
  import HopperLogo from '$lib/brand/HopperLogo.svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { api, ApiError } from '$lib/api/client';

  // 'request' asks for the email; 'reset' collects the code + new password.
  let step = $state<'request' | 'reset'>('request');
  let email = $state('');
  let code = $state('');
  let password = $state('');
  let submitting = $state(false);
  let error = $state<string | null>(null);
  let resent = $state(false);

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
    if (password.length < 12) {
      error = 'Password must be at least 12 characters.';
      return;
    }
    submitting = true;
    try {
      await api.post('/auth/reset-password', { email, code, password });
      window.location.href = '/login?reset=1';
    } catch (err) {
      error = err instanceof ApiError ? err.message : 'Reset failed. Please try again.';
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

<div class="grid min-h-[100dvh] place-items-center bg-background px-6 py-10">
  <div class="w-full max-w-sm">
    <div class="mb-8 flex items-center gap-3">
      <HopperLogo size={36} idle />
      <span class="text-lg font-semibold tracking-tight">Hopper</span>
    </div>

    <h1 class="text-2xl font-bold tracking-tight">Reset your password</h1>
    <p class="mt-1 mb-6 text-sm text-muted-foreground">
      {#if step === 'request'}
        Enter your email and we'll send you a reset code.
      {:else}
        Enter the code sent to <span class="font-medium text-foreground">{email}</span> and choose a new password.
      {/if}
    </p>

    {#if error}
      <div class="mb-5 flex items-start gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
        <AlertCircle class="mt-0.5 size-4 shrink-0" />
        <span>{error}</span>
      </div>
    {/if}

    {#if step === 'request'}
      <form onsubmit={requestCode} class="space-y-4">
        <div>
          <Label for="fp-email">Email</Label>
          <Input id="fp-email" type="email" bind:value={email} required autocomplete="email" placeholder="you@example.com" class="mt-1" />
        </div>
        <Button type="submit" disabled={submitting} size="lg" class="group h-12 w-full justify-between text-[15px] shadow-sm">
          <span class="flex items-center gap-2.5">
            {#if submitting}<Spinner class="size-4" /> Sending…{:else}Send reset code{/if}
          </span>
          {#if !submitting}<ArrowRight class="size-4 transition-transform group-hover:translate-x-1" />{/if}
        </Button>
      </form>
    {:else}
      <form onsubmit={reset} class="space-y-4">
        <div>
          <Label for="fp-code">Reset code</Label>
          <Input id="fp-code" bind:value={code} required inputmode="numeric" autocomplete="one-time-code" placeholder="123456" class="mt-1 text-center text-lg tracking-[0.4em]" />
        </div>
        <div>
          <Label for="fp-password">New password</Label>
          <Input id="fp-password" type="password" bind:value={password} required autocomplete="new-password" placeholder="At least 12 characters" class="mt-1" />
        </div>
        <Button type="submit" disabled={submitting} size="lg" class="group h-12 w-full justify-between text-[15px] shadow-sm">
          <span class="flex items-center gap-2.5">
            {#if submitting}<Spinner class="size-4" /> Resetting…{:else}<KeyRound class="size-4" /> Reset password{/if}
          </span>
          {#if !submitting}<ArrowRight class="size-4 transition-transform group-hover:translate-x-1" />{/if}
        </Button>
        <div class="flex items-center justify-between text-sm">
          <button type="button" onclick={() => { step = 'request'; error = null; }} class="text-muted-foreground hover:underline">← Back</button>
          <button type="button" onclick={resend} class="font-medium text-foreground hover:underline">Resend code</button>
        </div>
        {#if resent}
          <p class="flex items-center gap-1.5 text-xs text-muted-foreground"><Check class="size-3.5" /> A new code is on its way.</p>
        {/if}
      </form>
    {/if}

    <p class="mt-6 text-center text-sm text-muted-foreground">
      <a href="/login" data-sveltekit-reload class="font-medium text-foreground hover:underline">Back to sign in</a>
    </p>
  </div>
</div>
