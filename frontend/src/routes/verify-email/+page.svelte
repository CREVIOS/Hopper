<script lang="ts">
  import { ShieldCheck, ArrowRight, AlertCircle, Check } from 'lucide-svelte';
  import { page } from '$app/state';
  import { Button, Input, Label } from '$lib/ui';
  import HopperLogo from '$lib/brand/HopperLogo.svelte';
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

<div class="grid min-h-[100dvh] place-items-center bg-background px-6 py-10">
  <div class="w-full max-w-sm">
    <div class="mb-8 flex items-center gap-3">
      <HopperLogo size={36} idle />
      <span class="text-lg font-semibold tracking-tight">Hopper</span>
    </div>

    <h1 class="text-2xl font-bold tracking-tight">Verify your email</h1>
    <p class="mt-1 mb-6 text-sm text-muted-foreground">
      Enter the 6-digit code we emailed you to activate your account.
    </p>

    {#if error}
      <div class="mb-5 flex items-start gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
        <AlertCircle class="mt-0.5 size-4 shrink-0" />
        <span>{error}</span>
      </div>
    {/if}

    <form onsubmit={verify} class="space-y-4">
      <div>
        <Label for="ve-email">Email</Label>
        <Input id="ve-email" type="email" bind:value={email} required autocomplete="email" placeholder="you@example.com" class="mt-1" />
      </div>
      <div>
        <Label for="ve-code">Verification code</Label>
        <Input id="ve-code" bind:value={code} required inputmode="numeric" autocomplete="one-time-code" placeholder="123456" class="mt-1 text-center text-lg tracking-[0.4em]" />
      </div>
      <Button type="submit" disabled={submitting} size="lg" class="group h-12 w-full justify-between text-[15px] shadow-sm">
        <span class="flex items-center gap-2.5">
          {#if submitting}<Spinner class="size-4" /> Verifying…{:else}<ShieldCheck class="size-4" /> Verify{/if}
        </span>
        {#if !submitting}<ArrowRight class="size-4 transition-transform group-hover:translate-x-1" />{/if}
      </Button>
    </form>

    <div class="mt-4 flex items-center justify-between text-sm">
      <a href="/login" data-sveltekit-reload class="text-muted-foreground hover:underline">← Back to sign in</a>
      <button type="button" onclick={resend} class="font-medium text-foreground hover:underline">Resend code</button>
    </div>
    {#if resent}
      <p class="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground"><Check class="size-3.5" /> A new code is on its way.</p>
    {/if}
  </div>
</div>
