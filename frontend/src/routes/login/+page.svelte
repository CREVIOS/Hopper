<script lang="ts">
  import {
    Sparkles,
    Server,
    Cpu,
    KeyRound,
    Github,
    ShieldCheck,
    ArrowRight,
    AlertCircle
  } from 'lucide-svelte';
  import { page } from '$app/state';
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
</script>

<div class="grid min-h-screen bg-background lg:grid-cols-2">
  <!-- Brand panel -->
  <div
    class="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-primary via-primary to-info p-10 text-primary-foreground lg:flex"
  >
    <!-- decorative blobs -->
    <div
      class="pointer-events-none absolute -top-40 -left-32 size-[28rem] rounded-full bg-white/15 blur-3xl"
    ></div>
    <div
      class="pointer-events-none absolute -bottom-32 -right-32 size-[26rem] rounded-full bg-info/40 blur-3xl"
    ></div>
    <div
      class="pointer-events-none absolute inset-0 opacity-[0.07]"
      style="background-image: radial-gradient(circle at 1px 1px, white 1px, transparent 0); background-size: 24px 24px;"
    ></div>

    <div class="relative">
      <div class="flex items-center gap-2.5">
        <div class="flex size-9 items-center justify-center rounded-xl bg-white/20 backdrop-blur">
          <Sparkles class="size-5" />
        </div>
        <span class="text-xl font-bold tracking-tight">Hopper</span>
      </div>
    </div>

    <div class="relative max-w-md space-y-6">
      <h1 class="text-4xl font-bold leading-tight tracking-tight">
        University compute, <br />
        <span class="text-white/85">on demand.</span>
      </h1>
      <p class="text-lg text-white/80">
        A self-hosted VM cloud for students and researchers — slice bare-metal
        compute into isolated containers, billed per minute.
      </p>

      <ul class="mt-6 space-y-4">
        {#each features as f}
          <li class="flex gap-3">
            <div
              class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/15 backdrop-blur"
            >
              <f.icon class="size-4" />
            </div>
            <div>
              <div class="font-semibold">{f.title}</div>
              <div class="text-sm text-white/75">{f.desc}</div>
            </div>
          </li>
        {/each}
      </ul>
    </div>

    <div class="relative flex items-center gap-2 text-xs text-white/70">
      <ShieldCheck class="size-4" />
      <span>Secured by Keycloak OIDC · K8s + NATS · Open source</span>
    </div>
  </div>

  <!-- Sign-in panel -->
  <div class="flex items-center justify-center px-6 py-12 sm:px-10">
    <div class="w-full max-w-sm space-y-8">
      <div class="space-y-2 text-center lg:text-left">
        <div
          class="mx-auto flex size-11 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-info text-primary-foreground shadow-lg lg:mx-0"
        >
          <Sparkles class="size-5" />
        </div>
        <h2 class="text-2xl font-bold tracking-tight">Welcome back</h2>
        <p class="text-sm text-muted-foreground">
          Sign in with your university account to continue.
        </p>
      </div>

      {#if errorMessage}
        <div class="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertCircle class="mt-0.5 size-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      {/if}

      <Card class="overflow-hidden border-border/60">
        <CardContent class="p-6 pt-6">
          <Button
            onclick={handleLogin}
            disabled={signing}
            size="lg"
            class="w-full justify-between"
          >
            <span class="flex items-center gap-2">
              <ShieldCheck class="size-4" />
              {signing ? 'Redirecting…' : 'Continue with University SSO'}
            </span>
            <ArrowRight class="size-4" />
          </Button>

          <div class="my-6 flex items-center gap-3 text-xs text-muted-foreground">
            <div class="h-px flex-1 bg-border"></div>
            <span>What you'll get</span>
            <div class="h-px flex-1 bg-border"></div>
          </div>

          <ul class="space-y-2 text-sm text-muted-foreground">
            <li class="flex items-center gap-2">
              <span class="size-1.5 rounded-full bg-success"></span>
              Browser terminal + VS Code
            </li>
            <li class="flex items-center gap-2">
              <span class="size-1.5 rounded-full bg-success"></span>
              Per-minute credit billing
            </li>
            <li class="flex items-center gap-2">
              <span class="size-1.5 rounded-full bg-success"></span>
              Up to 3 concurrent VMs
            </li>
          </ul>
        </CardContent>
      </Card>

      <p class="text-center text-xs text-muted-foreground">
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
