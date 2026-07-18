<script lang="ts">
  import {
    GraduationCap,
    UserRound,
    AlertCircle,
    Check,
    UserPlus,
    MailCheck,
    Mail,
    Lock,
    Eye,
    EyeOff
  } from 'lucide-svelte';
  import { Button } from '$lib/ui';
  import AuthLayout from '$lib/auth/AuthLayout.svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { api, ApiError } from '$lib/api/client';
  import { page } from '$app/state';
  import PasswordRequirements from '$lib/auth/PasswordRequirements.svelte';
  import { explainFailures, unmetRules } from '$lib/auth/passwordPolicy';

  let name = $state('');
  // Prefilled when the landing-page email capture hands the address over.
  let email = $state(page.url.searchParams.get('email') ?? '');
  let password = $state('');
  let showPw = $state(false);
  let role = $state<'student' | 'teacher'>('student');
  let submitting = $state(false);
  let error = $state<string | null>(null);
  let passwordRejected = $state(false);

  // Two-step flow: 'form' collects details, 'verify' collects the emailed code.
  let step = $state<'form' | 'verify'>('form');
  let code = $state('');
  let pendingTeacher = $state(false);
  let resent = $state(false);

  const roles = [
    { value: 'student', label: 'Student', desc: 'Launch VMs with credits from your teacher.', icon: UserRound },
    { value: 'teacher', label: 'Teacher', desc: 'Allocate credits to students (needs approval).', icon: GraduationCap }
  ] as const;

  async function submit(e: SubmitEvent) {
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
      const res = await api.post<{ pending_teacher?: boolean }>('/auth/signup', {
        name,
        email,
        password,
        role
      });
      pendingTeacher = !!res?.pending_teacher;
      step = 'verify';
    } catch (err) {
      error = err instanceof ApiError ? err.message : 'Sign-up failed. Please try again.';
      passwordRejected =
        err instanceof ApiError && err.status === 400 && /password/i.test(err.message);
    } finally {
      submitting = false;
    }
  }

  async function verify(e: SubmitEvent) {
    e.preventDefault();
    error = null;
    submitting = true;
    try {
      await api.post('/auth/verify-email', { email, code });
      await api.post('/auth/login', { email, password });
      window.location.href = pendingTeacher ? '/dashboard?welcome=teacher-pending' : '/dashboard';
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
    class="w-full max-w-[440px] rounded-3xl border border-white bg-white/95 p-8 shadow-2xl shadow-indigo-950/10 backdrop-blur-sm dark:border-white/10 dark:bg-slate-900/90 sm:p-9"
  >
    <div class="flex flex-col items-center gap-4 text-center">
      <div
        class="grid size-14 place-items-center rounded-2xl bg-white shadow-md ring-1 ring-slate-100 dark:bg-slate-800 dark:ring-white/10"
      >
        {#if step === 'form'}
          <UserPlus class="size-6 text-slate-900 dark:text-white" strokeWidth={2} />
        {:else}
          <MailCheck class="size-6 text-slate-900 dark:text-white" strokeWidth={2} />
        {/if}
      </div>
      <div class="space-y-1.5">
        <h1 class="text-[1.6rem] font-bold leading-tight tracking-tight">
          {step === 'form' ? 'Create your account' : 'Verify your email'}
        </h1>
        <p class="text-sm text-muted-foreground">
          {#if step === 'form'}
            Start deploying cloud VMs in minutes.
          {:else}
            We sent a 6-digit code to <span class="font-medium text-foreground">{email}</span>.
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

    {#if step === 'verify'}
      <form onsubmit={verify} class="mt-6 space-y-4">
        <input
          bind:value={code}
          required
          inputmode="numeric"
          autocomplete="one-time-code"
          placeholder="000000"
          class="h-14 w-full rounded-xl border border-input bg-secondary/60 text-center text-2xl font-bold tracking-[0.5em] outline-none ring-ring/50 transition focus:border-ring focus:bg-background focus:ring-2 dark:bg-secondary/40"
        />
        <Button type="submit" disabled={submitting} class="h-11 w-full rounded-xl text-[15px] font-semibold">
          {#if submitting}<Spinner class="size-4" /> Verifying…{:else}Verify & continue{/if}
        </Button>
        <div class="flex items-center justify-between text-sm">
          <button type="button" onclick={() => { step = 'form'; error = null; }} class="text-muted-foreground hover:underline">← Back</button>
          <button type="button" onclick={resend} class="font-medium text-primary hover:underline">Resend code</button>
        </div>
        {#if resent}
          <p class="flex items-center gap-1.5 text-xs text-muted-foreground"><Check class="size-3.5" /> A new code is on its way.</p>
        {/if}
      </form>
    {:else}
      <form onsubmit={submit} class="mt-6 space-y-4">
        <div class="grid grid-cols-2 gap-2.5">
          {#each roles as r}
            <button
              type="button"
              onclick={() => (role = r.value)}
              class={`relative flex flex-col items-start gap-1 rounded-xl border p-3 text-left transition-colors ${
                role === r.value
                  ? 'border-primary bg-primary/5 ring-1 ring-primary'
                  : 'border-border hover:bg-muted/50'
              }`}
            >
              <r.icon class={`size-4 ${role === r.value ? 'text-primary' : 'text-muted-foreground'}`} />
              <span class="text-sm font-semibold">{r.label}</span>
              <span class="text-[11px] leading-tight text-muted-foreground">{r.desc}</span>
              {#if role === r.value}
                <Check class="absolute right-2 top-2 size-3.5 text-primary" />
              {/if}
            </button>
          {/each}
        </div>

        <input
          bind:value={name}
          required
          autocomplete="name"
          placeholder="Full name"
          class="h-11 w-full rounded-xl border border-input bg-secondary/60 px-3.5 text-sm outline-none ring-ring/50 transition focus:border-ring focus:bg-background focus:ring-2 dark:bg-secondary/40"
        />
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
        <div>
          <div class="relative">
            <Lock class="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type={showPw ? 'text' : 'password'}
              bind:value={password}
              required
              autocomplete="new-password"
              placeholder="Password"
              aria-describedby="su-password-reqs"
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
          <div id="su-password-reqs">
            <PasswordRequirements {password} username={email} showErrors={passwordRejected} />
          </div>
        </div>

        <Button type="submit" disabled={submitting} class="h-11 w-full rounded-xl text-[15px] font-semibold">
          {#if submitting}<Spinner class="size-4" /> Creating…{:else}Create account{/if}
        </Button>
      </form>
    {/if}

    <p class="mt-6 text-center text-sm text-muted-foreground">
      Already have an account?
      <a href="/login" data-sveltekit-reload class="font-semibold text-primary hover:underline">Sign in</a>
    </p>
  </div>
</AuthLayout>
