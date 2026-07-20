<script lang="ts">
  import { onMount } from 'svelte';
  import { Code2, ArrowLeft, RefreshCw, Check, AlertCircle } from 'lucide-svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import HopperLogo from '$lib/brand/HopperLogo.svelte';
  import { Button } from '$lib/ui';
  import { shortId } from '$lib/utils';
  import type { Pod } from '$lib/types';

  let { data }: { data: { pod: Pod | null; userId: string } } = $props();

  // The real code-server URL this page hands off to once it's warm.
  const codeBase = $derived(
    data.pod ? `/${data.userId}/code/${data.pod.id}/` : ''
  );
  // Open straight into the persistent per-user workspace (FR-HC-28) so files
  // from previous sessions are right there instead of an empty editor.
  const codeUrl = $derived(codeBase ? `${codeBase}?folder=/workspace` : '');

  type Phase = 'checking' | 'warming' | 'opening' | 'error' | 'not-running';
  let phase = $state<Phase>('checking');
  let attempts = $state(0);
  let errorDetail = $state('');

  const MAX_WAIT_MS = 90_000;
  const POLL_MS = 1_500;

  // Step list rendered in the splash — index advances with the phase.
  const steps = [
    { key: 'checking', label: 'Checking your VM' },
    { key: 'warming', label: 'Starting code-server' },
    { key: 'opening', label: 'Opening the editor' }
  ];
  const stepIndex = $derived(
    phase === 'checking' ? 0 : phase === 'warming' ? 1 : phase === 'opening' ? 2 : -1
  );

  async function pollUntilReady() {
    const started = Date.now();
    phase = 'warming';
    while (Date.now() - started < MAX_WAIT_MS) {
      attempts += 1;
      try {
        const res = await fetch(`${codeBase}healthz`, {
          credentials: 'same-origin',
          cache: 'no-store'
        });
        if (res.ok) {
          phase = 'opening';
          // Give the paint a beat so "Opening the editor" registers, then swap
          // this tab for VS Code (replace → no launcher in the back stack).
          setTimeout(() => location.replace(codeUrl), 450);
          return;
        }
        if (res.status === 401 || res.status === 403 || res.status === 404) {
          const body = await res.json().catch(() => null);
          errorDetail = body?.detail ?? `VS Code proxy returned ${res.status}.`;
          phase = 'error';
          return;
        }
        // 502/503 → still warming; fall through to the next poll.
      } catch {
        // network hiccup — keep polling
      }
      await new Promise((r) => setTimeout(r, POLL_MS));
    }
    errorDetail = 'code-server did not come up in time. The VM may still be installing extensions on first boot.';
    phase = 'error';
  }

  function retry() {
    errorDetail = '';
    attempts = 0;
    pollUntilReady();
  }

  onMount(() => {
    if (!data.pod) {
      errorDetail = 'VM not found.';
      phase = 'error';
      return;
    }
    if (data.pod.state !== 'running') {
      phase = 'not-running';
      return;
    }
    pollUntilReady();
  });
</script>

<svelte:head>
  <title>Opening VS Code · Hopper</title>
</svelte:head>

<!-- Fullscreen splash — sits above the app shell so the tab feels dedicated. -->
<div class="fixed inset-0 z-[60] flex flex-col items-center justify-center gap-8 bg-[#16161e] text-slate-200">
  <!-- soft brand glow -->
  <div
    class="pointer-events-none absolute left-1/2 top-1/3 h-[420px] w-[640px] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-30 blur-3xl"
    style="background: radial-gradient(closest-side, #6d5ef2, transparent 70%);"
  ></div>

  <div class="relative flex items-center gap-3">
    <HopperLogo size={34} />
    <span class="text-lg font-bold tracking-tight text-white">Hopper</span>
    <span class="text-slate-500">·</span>
    <span class="flex items-center gap-1.5 text-sm text-slate-400">
      <Code2 class="size-4" /> VS Code
    </span>
  </div>

  {#if phase === 'not-running'}
    <div class="relative flex max-w-sm flex-col items-center gap-4 text-center">
      <span class="grid size-14 place-items-center rounded-2xl bg-amber-500/10 text-amber-400 ring-1 ring-inset ring-amber-500/30">
        <AlertCircle class="size-6" />
      </span>
      <div>
        <p class="font-semibold text-white">VM isn't running</p>
        <p class="mt-1.5 text-sm leading-relaxed text-slate-400">
          {#if data.pod}
            <span class="font-mono">{shortId(data.pod.id, 8)}</span> is
            <span class="font-medium text-amber-400">{data.pod.state}</span>. VS Code is only
            available while the VM is running.
          {/if}
        </p>
      </div>
      <Button href={data.pod ? `/pods/${data.pod.id}` : '/pods'} variant="secondary">
        <ArrowLeft class="size-4" /> Back to VM
      </Button>
    </div>
  {:else if phase === 'error'}
    <div class="relative flex max-w-sm flex-col items-center gap-4 text-center">
      <span class="grid size-14 place-items-center rounded-2xl bg-red-500/10 text-red-400 ring-1 ring-inset ring-red-500/30">
        <AlertCircle class="size-6" />
      </span>
      <div>
        <p class="font-semibold text-white">Couldn't open VS Code</p>
        <p class="mt-1.5 text-sm leading-relaxed text-slate-400">{errorDetail}</p>
      </div>
      <div class="flex items-center gap-2">
        <Button onclick={retry}>
          <RefreshCw class="size-4" /> Try again
        </Button>
        <Button href={data.pod ? `/pods/${data.pod.id}` : '/pods'} variant="secondary">
          <ArrowLeft class="size-4" /> Back to VM
        </Button>
      </div>
    </div>
  {:else}
    <div class="relative flex flex-col items-center gap-7">
      <!-- animated mark -->
      <div class="relative grid size-24 place-items-center">
        <svg viewBox="0 0 96 96" class="absolute inset-0 size-full -rotate-90">
          <circle cx="48" cy="48" r="43" fill="none" stroke="#2c2c3a" stroke-width="5" />
          <circle
            cx="48"
            cy="48"
            r="43"
            fill="none"
            stroke="#7c6cf5"
            stroke-width="5"
            stroke-linecap="round"
            stroke-dasharray="70 200"
            class="vsc-ring"
          />
        </svg>
        <span class="grid size-14 place-items-center rounded-2xl bg-[#1f1f2c] text-[#8b7cf8] ring-1 ring-inset ring-white/10">
          <Code2 class="size-7" />
        </span>
      </div>

      <div class="text-center">
        <p class="text-lg font-semibold tracking-tight text-white">
          {phase === 'opening' ? 'Opening the editor…' : 'Warming up VS Code'}
        </p>
        {#if data.pod}
          <p class="mt-1 font-mono text-sm text-slate-500">{shortId(data.pod.id, 12)}</p>
        {/if}
      </div>

      <!-- step list -->
      <ol class="space-y-2.5 text-sm">
        {#each steps as s, i (s.key)}
          <li class="flex items-center gap-2.5 transition-opacity duration-300 {i > stepIndex ? 'opacity-35' : ''}">
            {#if i < stepIndex}
              <span class="grid size-5 place-items-center rounded-full bg-emerald-500/15 text-emerald-400">
                <Check class="size-3" />
              </span>
            {:else if i === stepIndex}
              <span class="grid size-5 place-items-center text-[#8b7cf8]">
                <Spinner class="size-4" />
              </span>
            {:else}
              <span class="grid size-5 place-items-center">
                <span class="size-1.5 rounded-full bg-slate-600"></span>
              </span>
            {/if}
            <span class={i === stepIndex ? 'font-medium text-slate-200' : 'text-slate-400'}>
              {s.label}
            </span>
          </li>
        {/each}
      </ol>

      {#if attempts > 6}
        <p class="max-w-xs text-center text-xs leading-relaxed text-slate-500">
          First boot can take up to a minute while code-server initializes — hang tight.
        </p>
      {/if}
    </div>
  {/if}

  <p class="absolute bottom-6 text-xs text-slate-600">
    This tab becomes your editor — no need to close it.
  </p>
</div>

<style>
  @keyframes vscSpin {
    to { transform: rotate(360deg); }
  }
  .vsc-ring {
    animation: vscSpin 0.9s linear infinite;
    transform-origin: center;
    transform-box: fill-box;
  }
  @media (prefers-reduced-motion: reduce) {
    .vsc-ring { animation: none; }
  }
</style>
