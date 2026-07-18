<script lang="ts">
  import {
    Server,
    Cpu,
    KeyRound,
    Github,
    ShieldCheck,
    ArrowRight,
    AlertCircle,
    TerminalSquare,
    Coins,
    Layers,
    Check
  } from 'lucide-svelte';
  import { page } from '$app/state';
  import { dev } from '$app/environment';
  import { Button, Input, Label } from '$lib/ui';
  import HopperLogo from '$lib/brand/HopperLogo.svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { api, ApiError } from '$lib/api/client';

  let signing = $state(false);

  // Themed email + password login (direct grant). SSO button below still works.
  let email = $state('');
  let password = $state('');
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
      default:
        return null;
    }
  });
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

  // Clicking "Sign in as admin" does a full-page nav to Keycloak. If the user
  // hits browser Back, this page is restored from the bfcache with `signing`
  // still true, leaving the button stuck on "Redirecting…". Reset it whenever
  // the page is shown (pageshow fires on bfcache restores too).
  function handlePageShow() {
    signing = false;
  }

  const features = [
    {
      icon: Server,
      title: 'Spin up VMs in seconds',
      desc: 'Pre-built images for ML, C++, Java and bare Ubuntu, one click.'
    },
    {
      icon: Cpu,
      title: 'Live metrics + terminal',
      desc: 'Real-time CPU/RAM and an in-browser shell from any device.'
    },
    {
      icon: KeyRound,
      title: 'SSH & VS Code in browser',
      desc: 'Forward keys, connect via SSH, or open VS Code right here.'
    }
  ];

  // Small modest accent colors for the "what you'll get" chips — purely visual.
  const perks = [
    { icon: TerminalSquare, label: 'Browser terminal + VS Code', tint: 'text-primary bg-primary/10' },
    { icon: Coins, label: 'Per-minute credit billing', tint: 'text-success bg-success/10' },
    { icon: Layers, label: 'Up to 3 concurrent VMs', tint: 'text-info bg-info/10' }
  ];
</script>

<svelte:window onpageshow={handlePageShow} />

<div class="grid min-h-[100dvh] bg-background lg:grid-cols-[1.1fr_1fr]">
  <!-- Brand panel: a fixed deep-indigo surface in both themes (split-login
       convention), textured with a faint dot grid instead of floating blobs. -->
  <aside class="brand-panel relative hidden flex-col justify-between overflow-hidden p-8 text-white lg:flex xl:p-12">
    <div class="dot-grid pointer-events-none absolute inset-0 opacity-[0.4]"></div>
    <div
      class="pointer-events-none absolute inset-0"
      style="background:radial-gradient(80% 60% at 12% 8%, hsl(252 90% 70% / 0.20), transparent 60%);"
    ></div>
    <div class="pointer-events-none absolute inset-x-0 bottom-0 h-48 bg-gradient-to-t from-black/40 to-transparent"></div>

    <!-- Wordmark lockup — the animated Hopper mark. -->
    <div class="animate-fade-up relative flex items-center gap-3">
      <HopperLogo size={40} idle />
      <span class="text-lg font-semibold tracking-tight">Hopper</span>
    </div>

    <div class="relative max-w-lg">
      <p
        class="animate-fade-up mb-5 font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-white/45"
        style="animation-delay: 40ms"
      >
        Self-hosted, built for campus
      </p>
      <h1
        class="animate-fade-up text-[2.75rem] font-bold leading-[1.05] tracking-tight xl:text-6xl"
        style="animation-delay: 80ms; text-wrap: balance"
      >
        University compute,
        <span class="text-white/55">on demand.</span>
      </h1>
      <p
        class="animate-fade-up mt-5 max-w-md text-[15px] leading-relaxed text-white/65"
        style="animation-delay: 120ms"
      >
        A self-hosted VM cloud for students and researchers. Slice bare-metal
        compute into isolated containers, billed by the minute.
      </p>

      <ul class="mt-10 divide-y divide-white/10 border-y border-white/10">
        {#each features as f, i}
          <li
            class="feature-row animate-fade-up flex items-start gap-4 py-4 transition-colors hover:bg-white/[0.04]"
            style="animation-delay: {160 + i * 70}ms"
          >
            <span class="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-white/[0.06] ring-1 ring-inset ring-white/10">
              <f.icon class="size-[1.05rem]" strokeWidth={1.75} />
            </span>
            <div class="min-w-0">
              <div class="font-medium leading-tight">{f.title}</div>
              <div class="mt-1 text-sm leading-snug text-white/55">{f.desc}</div>
            </div>
          </li>
        {/each}
      </ul>
    </div>

    <div
      class="animate-fade-up relative flex items-center gap-2 text-xs text-white/45"
      style="animation-delay: 420ms"
    >
      <ShieldCheck class="size-4" strokeWidth={1.75} />
      <span>Secured by Keycloak OIDC. Open source, K8s + NATS.</span>
    </div>
  </aside>

  <!-- Sign-in panel -->
  <main class="relative flex items-center justify-center px-6 py-10 sm:px-10">
    <div class="relative w-full max-w-sm">
      <div class="animate-fade-up mb-8 text-center lg:text-left">
        <h2 class="text-[1.7rem] font-bold leading-tight tracking-tight">Welcome back</h2>
        <p class="mt-1 text-sm text-muted-foreground">
          Sign in with your university account to continue.
        </p>
      </div>

      {#if errorMessage || formError}
        <div
          class="animate-scale-in mb-5 flex items-start gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
        >
          <AlertCircle class="mt-0.5 size-4 shrink-0" />
          <span>{formError ?? errorMessage}</span>
        </div>
      {:else if successMessage}
        <div
          class="animate-scale-in mb-5 flex items-start gap-2.5 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-600 dark:text-emerald-400"
        >
          <Check class="mt-0.5 size-4 shrink-0" />
          <span>{successMessage}</span>
        </div>
      {/if}

      <!-- Themed email + password sign-in -->
      <form onsubmit={handlePasswordLogin} class="animate-fade-up space-y-3.5" style="animation-delay: 40ms">
        <div>
          <Label for="li-email">Email</Label>
          <Input id="li-email" type="email" bind:value={email} required autocomplete="email" placeholder="you@example.com" class="mt-1" />
        </div>
        <div>
          <div class="flex items-center justify-between">
            <Label for="li-password">Password</Label>
            <a href="/forgot-password" class="text-xs font-medium text-muted-foreground hover:text-foreground hover:underline">Forgot password?</a>
          </div>
          <Input id="li-password" type="password" bind:value={password} required autocomplete="current-password" placeholder="Your password" class="mt-1" />
        </div>
        {#if needsVerify}
          <p class="text-sm text-muted-foreground">
            <a href={`/verify-email?email=${encodeURIComponent(email)}`} class="font-medium text-foreground underline underline-offset-2">Verify your email</a>
            to finish setting up your account.
          </p>
        {/if}
        <Button type="submit" disabled={submitting} size="lg" class="group h-12 w-full justify-between text-[15px] shadow-sm">
          <span class="flex items-center gap-2.5">
            {#if submitting}<Spinner class="size-4" /> Signing in…{:else}<KeyRound class="size-4" /> Sign in{/if}
          </span>
          {#if !submitting}<ArrowRight class="size-4 transition-transform group-hover:translate-x-1" />{/if}
        </Button>
      </form>

      <p class="animate-fade-up mt-3 text-center text-sm text-muted-foreground" style="animation-delay: 50ms">
        New here?
        <a href="/signup" data-sveltekit-reload class="font-medium text-foreground hover:underline">Create an account</a>
      </p>

      <!-- Divider -->
      <div class="animate-fade-up my-5 flex items-center gap-3 text-xs text-muted-foreground" style="animation-delay: 55ms">
        <span class="h-px flex-1 bg-border"></span> or <span class="h-px flex-1 bg-border"></span>
      </div>

      <Button
        onclick={handleLogin}
        disabled={signing}
        variant="outline"
        size="lg"
        class="group animate-fade-up h-12 w-full justify-between text-[15px] shadow-sm"
        style="animation-delay: 60ms"
      >
        <span class="flex items-center gap-2.5">
          <ShieldCheck class="size-4" />
          {signing ? 'Redirecting…' : 'Sign in as admin'}
        </span>
        <ArrowRight class="size-4 transition-transform group-hover:translate-x-1" />
      </Button>

      <p class="animate-fade-up mt-2 text-center text-xs text-muted-foreground" style="animation-delay: 65ms">
        Administrators sign in with their admin username and password.
      </p>

      {#if dev}
        <!-- Dev-only: the real SSO flow can't complete on localhost (backend
             returns the Keycloak callback to the deployed host). These mint a
             token directly and set the session cookies. Never ship — the
             /dev-login endpoint 404s outside `vite dev`. -->
        <div class="animate-fade-up mt-2.5 grid grid-cols-2 gap-2.5" style="animation-delay: 90ms">
          <a
            href="/dev-login?as=admin"
            data-sveltekit-reload
            class="flex items-center justify-center gap-2 rounded-md border border-dashed border-warning/50 bg-warning/5 px-3 py-2 text-sm font-medium text-warning transition-colors hover:bg-warning/10"
          >
            <KeyRound class="size-4" /> Dev: admin
          </a>
          <a
            href="/dev-login?as=user"
            data-sveltekit-reload
            class="flex items-center justify-center gap-2 rounded-md border border-dashed border-warning/50 bg-warning/5 px-3 py-2 text-sm font-medium text-warning transition-colors hover:bg-warning/10"
          >
            <KeyRound class="size-4" /> Dev: user
          </a>
        </div>
      {/if}

      <!-- What you'll get -->
      <div class="animate-fade-up mt-8" style="animation-delay: 130ms">
        <p class="mb-3 font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
          What you'll get
        </p>
        <ul class="space-y-px">
          {#each perks as p}
            <li class="flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-muted/50">
              <span class="grid size-7 shrink-0 place-items-center rounded-md {p.tint}">
                <p.icon class="size-4" strokeWidth={1.75} />
              </span>
              <span class="min-w-0 text-sm font-medium text-foreground">{p.label}</span>
              <Check class="ml-auto size-4 shrink-0 text-success/70" />
            </li>
          {/each}
        </ul>
      </div>

      <div
        class="animate-fade-up mt-6 border-t border-border pt-5 text-xs leading-relaxed text-muted-foreground"
        style="animation-delay: 170ms"
      >
        <p class="font-medium text-foreground">Students and teachers welcome.</p>
        <p class="mt-1.5">
          Create an account with your email and sign in
          above. Teacher accounts are reviewed by an admin before they can
          allocate credits. Administrators sign in with their admin username and
          password. Trouble? Email
          <a class="font-medium text-foreground underline underline-offset-2" href="mailto:hopper-admin@cs.du.ac.bd">
            hopper-admin@cs.du.ac.bd
          </a>.
        </p>
      </div>

      <p
        class="animate-fade-up mt-5 text-center text-xs text-muted-foreground lg:text-left"
        style="animation-delay: 210ms"
      >
        Trouble signing in?
        <a
          href="https://github.com/anthropics/hopper"
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex items-center gap-1 font-medium text-foreground hover:underline"
        >
          <Github class="size-3" /> Open an issue
        </a>
      </p>
    </div>
  </main>
</div>

<style>
  /* Fixed deep-indigo brand surface, consistent across light & dark themes. */
  .brand-panel {
    background:
      linear-gradient(160deg, hsl(250 47% 10%) 0%, hsl(255 48% 13%) 55%, hsl(258 50% 16%) 100%);
  }
  /* Faint dot grid — sits still, no GPU-thrashing drift. */
  .dot-grid {
    background-image: radial-gradient(hsl(0 0% 100% / 0.07) 1px, transparent 1px);
    background-size: 22px 22px;
  }
  .feature-row:hover :global(svg) {
    transform: scale(1.06);
  }
  .feature-row :global(svg) {
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  }
  @media (prefers-reduced-motion: reduce) {
    .feature-row:hover :global(svg) {
      transform: none;
    }
  }
</style>
