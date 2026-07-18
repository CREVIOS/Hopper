<script lang="ts">
  import type { Snippet } from 'svelte';
  import { Cpu, SquareTerminal, Cloud, Server, Code2, Rabbit } from 'lucide-svelte';
  import HopperLogo from '$lib/brand/HopperLogo.svelte';

  let { children }: { children: Snippet } = $props();

  // Floating Hopper-themed chips that flank the centered card (desktop only).
  // Positions are percentages of the viewport; centred on their own origin.
  const chips = [
    { Icon: Cpu, top: 21, left: 15, color: 'text-indigo-500', bg: 'bg-indigo-50', rot: -8 },
    { Icon: SquareTerminal, top: 55, left: 21, color: 'text-cyan-600', bg: 'bg-cyan-50', rot: 6 },
    { Icon: Code2, top: 83, left: 27, color: 'text-violet-500', bg: 'bg-violet-50', rot: -5 },
    { Icon: Cloud, top: 17, left: 79, color: 'text-sky-500', bg: 'bg-sky-50', rot: 7 },
    { Icon: Server, top: 51, left: 81, color: 'text-emerald-600', bg: 'bg-emerald-50', rot: -6 },
    { Icon: Rabbit, top: 12, left: 43, color: 'text-indigo-600', bg: 'bg-indigo-50', rot: -4 }
  ];
  const dots = [
    { top: 30, left: 37 },
    { top: 26, left: 68 },
    { top: 40, left: 30 },
    { top: 68, left: 75 },
    { top: 86, left: 39 },
    { top: 74, left: 61 }
  ];
</script>

<div
  class="relative min-h-[100dvh] overflow-hidden bg-gradient-to-b from-indigo-50/80 via-white to-violet-50/60 dark:from-slate-950 dark:via-slate-950 dark:to-indigo-950/40"
>
  <!-- Soft radial glow behind the card -->
  <div
    class="pointer-events-none absolute left-1/2 top-[-12%] h-[680px] w-[960px] -translate-x-1/2 rounded-full opacity-70 blur-3xl"
    style="background: radial-gradient(closest-side, rgba(196,181,253,0.55), transparent 72%);"
  ></div>

  <!-- Orbit arcs -->
  <div class="pointer-events-none absolute inset-0 hidden md:block">
    <div
      class="absolute left-1/2 top-[62%] size-[1500px] -translate-x-1/2 rounded-full border border-indigo-200/60 dark:border-white/[0.05]"
    ></div>
    <div
      class="absolute left-[38%] top-[-46%] size-[1100px] rounded-full border border-violet-200/60 dark:border-white/[0.05]"
    ></div>
    <div
      class="absolute left-[54%] top-[18%] size-[1300px] rounded-full border border-sky-200/50 dark:border-white/[0.04]"
    ></div>
  </div>

  <!-- Floating chips + sparkle dots -->
  <div class="pointer-events-none absolute inset-0 hidden md:block">
    {#each chips as c}
      <div
        class="absolute grid size-[60px] place-items-center rounded-2xl border border-white {c.bg} shadow-xl shadow-slate-900/10 dark:border-white/10 dark:bg-slate-900/80 dark:shadow-black/40"
        style="top:{c.top}%; left:{c.left}%; transform: translate(-50%,-50%) rotate({c.rot}deg);"
      >
        <c.Icon class="size-7 {c.color} dark:opacity-90" strokeWidth={1.75} />
      </div>
    {/each}
    {#each dots as d}
      <div
        class="absolute size-2 rounded-full bg-indigo-300/70 dark:bg-indigo-400/40"
        style="top:{d.top}%; left:{d.left}%;"
      ></div>
    {/each}
  </div>

  <!-- Brand lockup -->
  <a href="/" class="absolute left-8 top-8 z-10 flex items-center gap-2.5">
    <HopperLogo size={34} />
    <span class="text-lg font-bold tracking-tight text-slate-900 dark:text-white">Hopper</span>
  </a>

  <!-- Centered card -->
  <div class="relative z-10 grid min-h-[100dvh] place-items-center px-6 py-16">
    {@render children()}
  </div>
</div>
