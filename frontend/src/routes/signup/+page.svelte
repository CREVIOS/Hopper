<script lang="ts">
  import { GraduationCap, UserRound, ShieldCheck, ArrowRight, AlertCircle, Check } from 'lucide-svelte';
  import { Button, Input, Label } from '$lib/ui';
  import HopperLogo from '$lib/brand/HopperLogo.svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { api, ApiError } from '$lib/api/client';

  let name = $state('');
  let email = $state('');
  let password = $state('');
  let role = $state<'student' | 'teacher'>('student');
  let submitting = $state(false);
  let error = $state<string | null>(null);

  const roles = [
    { value: 'student', label: 'Student', desc: 'Launch VMs with credits from your teacher.', icon: UserRound },
    { value: 'teacher', label: 'Teacher', desc: 'Allocate credits to students (needs admin approval).', icon: GraduationCap }
  ] as const;

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    error = null;
    if (password.length < 8) {
      error = 'Password must be at least 8 characters.';
      return;
    }
    submitting = true;
    try {
      const res = await api.post<{ pending_teacher?: boolean }>('/auth/signup', {
        name,
        email,
        password,
        role
      });
      // Full navigation so SSR picks up the freshly-set session cookies.
      const dest = res?.pending_teacher ? '/dashboard?welcome=teacher-pending' : '/dashboard';
      window.location.href = dest;
    } catch (err) {
      error = err instanceof ApiError ? err.message : 'Sign-up failed. Please try again.';
      submitting = false;
    }
  }
</script>

<div class="grid min-h-[100dvh] bg-background lg:grid-cols-[1.1fr_1fr]">
  <!-- Brand panel -->
  <aside class="brand-panel relative hidden flex-col justify-between overflow-hidden p-8 text-white lg:flex xl:p-12">
    <div class="dot-grid pointer-events-none absolute inset-0 opacity-[0.4]"></div>
    <div class="animate-fade-up relative flex items-center gap-3">
      <HopperLogo size={40} idle />
      <span class="text-lg font-semibold tracking-tight">Hopper</span>
    </div>
    <div class="relative max-w-lg">
      <p class="animate-fade-up mb-5 font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-white/45" style="animation-delay: 40ms">
        Join your campus cloud
      </p>
      <h1 class="animate-fade-up text-[2.75rem] font-bold leading-[1.05] tracking-tight xl:text-6xl" style="animation-delay: 80ms; text-wrap: balance">
        Create your
        <span class="text-white/55">Hopper account.</span>
      </h1>
      <p class="animate-fade-up mt-5 max-w-md text-[15px] leading-relaxed text-white/65" style="animation-delay: 120ms">
        Students launch VMs with credits allocated by their teachers. Teachers
        manage a credit budget for their class. Sign up with your university email.
      </p>
    </div>
    <div class="animate-fade-up relative flex items-center gap-2 text-xs text-white/45" style="animation-delay: 420ms">
      <ShieldCheck class="size-4" strokeWidth={1.75} />
      <span>Secured by Keycloak. Only @cs.du.ac.bd accounts.</span>
    </div>
  </aside>

  <!-- Form panel -->
  <main class="relative flex items-center justify-center px-6 py-10 sm:px-10">
    <div class="relative w-full max-w-sm">
      <div class="animate-fade-up mb-8 text-center lg:text-left">
        <h2 class="text-[1.7rem] font-bold leading-tight tracking-tight">Create account</h2>
        <p class="mt-1 text-sm text-muted-foreground">Use your university email to get started.</p>
      </div>

      {#if error}
        <div class="animate-scale-in mb-5 flex items-start gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertCircle class="mt-0.5 size-4 shrink-0" />
          <span>{error}</span>
        </div>
      {/if}

      <form onsubmit={submit} class="animate-fade-up space-y-4" style="animation-delay: 60ms">
        <!-- Role selector -->
        <div>
          <Label>I am a…</Label>
          <div class="mt-1.5 grid grid-cols-2 gap-2.5">
            {#each roles as r}
              <button
                type="button"
                onclick={() => (role = r.value)}
                class={`relative flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors ${
                  role === r.value
                    ? 'border-primary bg-primary/5 ring-1 ring-primary'
                    : 'border-border hover:bg-muted/50'
                }`}
              >
                <r.icon class={`size-4 ${role === r.value ? 'text-primary' : 'text-muted-foreground'}`} />
                <span class="text-sm font-medium">{r.label}</span>
                <span class="text-[11px] leading-tight text-muted-foreground">{r.desc}</span>
                {#if role === r.value}
                  <Check class="absolute right-2 top-2 size-3.5 text-primary" />
                {/if}
              </button>
            {/each}
          </div>
        </div>

        <div>
          <Label for="su-name">Full name</Label>
          <Input id="su-name" bind:value={name} required autocomplete="name" placeholder="Jane Doe" class="mt-1" />
        </div>
        <div>
          <Label for="su-email">University email</Label>
          <Input id="su-email" type="email" bind:value={email} required autocomplete="email" placeholder="you@cs.du.ac.bd" class="mt-1" />
        </div>
        <div>
          <Label for="su-password">Password</Label>
          <Input id="su-password" type="password" bind:value={password} required autocomplete="new-password" placeholder="At least 8 characters" class="mt-1" />
        </div>

        <Button type="submit" disabled={submitting} size="lg" class="group h-12 w-full justify-between text-[15px] shadow-sm">
          <span class="flex items-center gap-2.5">
            {#if submitting}<Spinner class="size-4" /> Creating…{:else}Create account{/if}
          </span>
          {#if !submitting}<ArrowRight class="size-4 transition-transform group-hover:translate-x-1" />{/if}
        </Button>
      </form>

      <p class="animate-fade-up mt-6 text-center text-sm text-muted-foreground lg:text-left" style="animation-delay: 130ms">
        Already have an account?
        <a href="/login" data-sveltekit-reload class="font-medium text-foreground hover:underline">Sign in</a>
      </p>
    </div>
  </main>
</div>

<style>
  .brand-panel {
    background: linear-gradient(160deg, hsl(250 47% 10%) 0%, hsl(255 48% 13%) 55%, hsl(258 50% 16%) 100%);
  }
  .dot-grid {
    background-image: radial-gradient(hsl(0 0% 100% / 0.07) 1px, transparent 1px);
    background-size: 22px 22px;
  }
</style>
