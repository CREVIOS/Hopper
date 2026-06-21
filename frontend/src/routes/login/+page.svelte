<script lang="ts">
  import {
    Sparkles,
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
  import { Button, Card, CardContent } from '$lib/ui';

  let signing = $state(false);

  // Surface OAuth error redirects (?error=domain | email_unverified | oidc).
  const errorParam = $derived(page.url.searchParams.get('error'));
  const errorMessage = $derived.by(() => {
    switch (errorParam) {
      case 'domain':
        return 'Only @cs.du.ac.bd accounts may sign in. Contact your department admin if you need access.';
      case 'email_unverified':
        return 'Verify your email address (check your inbox), then sign in again.';
      case 'oidc':
        return 'Sign-in was cancelled or rejected by the identity provider.';
      default:
        return null;
    }
  });

  function handleLogin() {
    signing = true;
    window.location.href = '/api/auth/login';
  }

  const features = [
    {
      icon: Server,
      title: 'Spin up VMs in seconds',
      desc: 'Pre-built images for ML, C++, Java and bare Ubuntu — one click.'
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

<div class="grid min-h-screen bg-background lg:grid-cols-[1.05fr_1fr]">
  <!-- Brand panel -->
  <div
    class="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-primary to-info p-7 text-primary-foreground lg:flex xl:p-9"
  >
    <!-- soft neutral light — drifts slowly, no hue clash -->
    <div
      class="orb pointer-events-none absolute -top-44 -left-32 size-[34rem] rounded-full bg-white/10 blur-3xl"
    ></div>
    <div
      class="orb orb-slow pointer-events-none absolute -bottom-44 -right-28 size-[30rem] rounded-full bg-white/[0.07] blur-3xl"
    ></div>
    <!-- gentle bottom deepening for depth + footer legibility -->
    <div
      class="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/15 via-transparent to-transparent"
    ></div>
    <!-- subtle top sheen -->
    <div
      class="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent"
    ></div>

    <div class="animate-fade-up relative">
      <div class="flex items-center gap-2.5">
        <div
          class="flex size-9 items-center justify-center rounded-xl bg-white/20 shadow-lg shadow-black/10 ring-1 ring-inset ring-white/25 backdrop-blur"
        >
          <Sparkles class="size-5" />
        </div>
        <span class="text-xl font-bold tracking-tight">Hopper</span>
      </div>
    </div>

    <div class="relative max-w-md space-y-5">
      <div class="animate-fade-up space-y-3.5" style="animation-delay: 60ms">
        <span
          class="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-0.5 text-xs font-medium text-white/90 ring-1 ring-inset ring-white/20 backdrop-blur"
        >
          <span class="size-1.5 animate-pulse rounded-full bg-white"></span>
          Self-hosted · built for campus
        </span>
        <h1 class="text-4xl font-bold leading-[1.1] tracking-tight xl:text-5xl">
          University compute, <br />
          <span class="text-white/80">on demand.</span>
        </h1>
        <p class="max-w-md text-base leading-relaxed text-white/80">
          A self-hosted VM cloud for students and researchers — slice bare-metal
          compute into isolated containers, billed per minute.
        </p>
      </div>

      <ul class="space-y-1.5">
        {#each features as f, i}
          <li
            class="feature-row animate-fade-up flex gap-3 rounded-xl p-2 transition-colors hover:bg-white/10"
            style="animation-delay: {140 + i * 80}ms"
          >
            <div
              class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/15 ring-1 ring-inset ring-white/15 backdrop-blur transition-transform"
            >
              <f.icon class="size-[1.05rem]" />
            </div>
            <div>
              <div class="font-semibold">{f.title}</div>
              <div class="text-sm leading-snug text-white/75">{f.desc}</div>
            </div>
          </li>
        {/each}
      </ul>
    </div>

    <div
      class="animate-fade-up relative flex items-center gap-2 text-xs text-white/70"
      style="animation-delay: 420ms"
    >
      <ShieldCheck class="size-4" />
      <span>Secured by Keycloak OIDC · K8s + NATS · Open source</span>
    </div>
  </div>

  <!-- Sign-in panel -->
  <div class="surface-glow relative flex items-center justify-center px-6 py-8 sm:px-8">
    <!-- mobile-only ambient wash so the bare panel isn't flat on small screens -->
    <div
      class="pointer-events-none absolute -top-24 right-0 size-72 rounded-full bg-primary/10 blur-3xl lg:hidden"
    ></div>

    <div class="relative w-full max-w-sm space-y-5">
      <div class="animate-fade-up space-y-1.5 text-center lg:text-left">
        <div
          class="mx-auto flex size-11 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-info text-primary-foreground shadow-lg shadow-primary/25 lg:mx-0"
        >
          <Sparkles class="size-5" />
        </div>
        <h2 class="text-2xl font-bold tracking-tight">Welcome back</h2>
        <p class="text-sm text-muted-foreground">
          Sign in with your university account to continue.
        </p>
      </div>

      {#if errorMessage}
        <div
          class="animate-scale-in flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-2.5 text-sm text-destructive"
        >
          <AlertCircle class="mt-0.5 size-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      {/if}

      <Card
        class="animate-fade-up overflow-hidden border-border/60 shadow-lg shadow-black/[0.03]"
        style="animation-delay: 80ms"
      >
        <CardContent class="p-4 pt-4">
          <Button
            onclick={handleLogin}
            disabled={signing}
            size="lg"
            class="group w-full justify-between shadow-md shadow-primary/20"
          >
            <span class="flex items-center gap-2">
              <ShieldCheck class="size-4" />
              {signing ? 'Redirecting…' : 'Continue with University SSO'}
            </span>
            <ArrowRight class="size-4 transition-transform group-hover:translate-x-1" />
          </Button>

          {#if dev}
            <!-- Dev-only: the real SSO flow can't complete on localhost (backend
                 returns the Keycloak callback to the deployed host). This mints a
                 token directly and sets the session cookies. Never ships — the
                 /dev-login endpoint 404s outside `vite dev`. -->
            <a
              href="/dev-login"
              data-sveltekit-reload
              class="mt-2 flex w-full items-center justify-center gap-2 rounded-md border border-dashed border-warning/50 bg-warning/5 px-4 py-1.5 text-sm font-medium text-warning transition-colors hover:bg-warning/10"
            >
              <KeyRound class="size-4" /> Dev login (skip SSO)
            </a>
          {/if}

          <div class="my-4 flex items-center gap-3 text-xs text-muted-foreground">
            <div class="h-px flex-1 bg-border"></div>
            <span>What you'll get</span>
            <div class="h-px flex-1 bg-border"></div>
          </div>

          <ul class="space-y-1 text-sm">
            {#each perks as p}
              <li
                class="flex items-center gap-3 rounded-lg px-2 py-1 transition-colors hover:bg-muted/50"
              >
                <span
                  class="flex size-7 shrink-0 items-center justify-center rounded-md {p.tint}"
                >
                  <p.icon class="size-4" />
                </span>
                <span class="min-w-0 font-medium text-foreground">{p.label}</span>
                <Check class="ml-auto size-4 shrink-0 text-success/70" />
              </li>
            {/each}
          </ul>
        </CardContent>
      </Card>

      <div
        class="animate-fade-up rounded-lg border border-border/60 bg-muted/30 p-3 text-xs leading-relaxed text-muted-foreground"
        style="animation-delay: 160ms"
      >
        <p class="font-medium text-foreground">No sign-up form here — by design.</p>
        <p class="mt-1">
          Accounts are provisioned automatically through your university's single
          sign-on. There's nothing to register, and there is no password for Hopper
          to forget — if you can't log in, reset your <em>university</em> password
          through your institution's IdP, then come back and click
          <span class="font-medium text-foreground">Continue with University SSO</span>.
        </p>
        <p class="mt-1.5">
          New student and not in the system yet? Email
          <a class="font-medium text-foreground underline" href="mailto:hopper-admin@cs.du.ac.bd">
            hopper-admin@cs.du.ac.bd
          </a>
          to be added.
        </p>
      </div>

      <p
        class="animate-fade-up text-center text-xs text-muted-foreground"
        style="animation-delay: 220ms"
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
  </div>
</div>

<style>
  /* Slow, modest drift on the brand-panel orbs — disabled for reduced-motion. */
  .orb {
    animation: orb-float 16s ease-in-out infinite;
  }
  .orb-slow {
    animation-duration: 22s;
    animation-direction: reverse;
  }
  @keyframes orb-float {
    0%,
    100% {
      transform: translate3d(0, 0, 0) scale(1);
    }
    50% {
      transform: translate3d(20px, -24px, 0) scale(1.06);
    }
  }
  .feature-row:hover :global(svg) {
    transform: scale(1.08);
  }
  @media (prefers-reduced-motion: reduce) {
    .orb {
      animation: none;
    }
  }
</style>
