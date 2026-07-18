<script lang="ts">
  import {
    Sparkles,
    ArrowRight,
    Server,
    ShieldCheck,
    Boxes,
    Radio,
    Minus,
    Plus,
    GraduationCap,
    Cpu,
    FlaskConical,
    Network,
    School
  } from 'lucide-svelte';
  import { goto } from '$app/navigation';
  import { Button } from '$lib/ui';
  import HopperLogo from '$lib/brand/HopperLogo.svelte';

  const SITE = 'https://hopper.farefin.com';
  const DESCRIPTION =
    'Hopper is a self-hosted campus cloud: SSH + VS Code virtual machines for students and teams, with per-minute credit billing and fair-share scheduling on your own cluster.';

  // Every link goes somewhere real — section anchors or auth routes.
  const navLinks = [
    ['Product', '#features'],
    ['How it works', '#flow'],
    ['FAQ', '#faq']
  ];
  const trusted = [
    { icon: GraduationCap, label: 'Univ. of Dhaka' },
    { icon: Cpu, label: 'CSE Dept' },
    { icon: FlaskConical, label: 'Research Lab' },
    { icon: Network, label: 'Systems Group' },
    { icon: School, label: 'EdTech BD' }
  ];

  // Hero email capture → carries the address into signup.
  let heroEmail = $state('');
  function startSignup() {
    const e = heroEmail.trim();
    goto(e ? `/signup?email=${encodeURIComponent(e)}` : '/signup');
  }

  // Two floating server racks. Each slot: two LED colours + a bar width.
  const leds = ['#c084fc', '#38bdf8', '#f59e0b', '#34d399', '#a78bfa', '#f472b6'];
  const barW = [62, 78, 50, 84, 66, 74, 56];

  let openFaq = $state(0);
  const faqs = [
    { q: 'What VM plans does Hopper offer?', a: 'Small, Medium and Large — sized by vCPU and memory. A VM reserves a quarter of its plan’s CPU and bursts to the full limit whenever cores are idle.' },
    { q: 'Do students get free credits to start?', a: 'Yes. New accounts get starter credits, and teachers can allocate more from their class budget at any time.' },
    { q: 'How does per-minute billing work?', a: 'Credits are charged by the minute while a VM runs, at the plan’s hourly rate. Stop the VM and billing stops immediately.' },
    { q: 'Can teachers manage a whole class?', a: 'Teachers allocate credit budgets to students, track every VM in real time, and approve access — all from the Teaching console.' },
    { q: 'How do I connect to a VM?', a: 'Connect over SSH with your key, or open a full VS Code workspace right in the browser. No local setup required.' }
  ];
</script>

<svelte:head>
  <meta name="description" content={DESCRIPTION} />
  <link rel="canonical" href="{SITE}/" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Hopper" />
  <meta property="og:title" content="Hopper — Cloud VMs for students & teams" />
  <meta property="og:description" content={DESCRIPTION} />
  <meta property="og:url" content="{SITE}/" />
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content="Hopper — Cloud VMs for students & teams" />
  <meta name="twitter:description" content={DESCRIPTION} />
  {@html `<script type="application/ld+json">${JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'Hopper',
    applicationCategory: 'DeveloperApplication',
    operatingSystem: 'Web',
    description: DESCRIPTION,
    url: SITE,
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' }
  })}</${'script'}>`}
</svelte:head>

<div class="relative min-h-[100dvh] overflow-hidden bg-gradient-to-b from-indigo-50/80 via-background to-violet-50/50 text-foreground dark:from-slate-950 dark:via-background dark:to-indigo-950/30">
  <!-- dot-grid texture -->
  <div
    class="pointer-events-none absolute inset-x-0 top-0 z-0 h-[720px] opacity-[0.5] [mask-image:radial-gradient(70%_60%_at_50%_0%,black,transparent)]"
    style="background-image: radial-gradient(circle at 1px 1px, rgba(99,102,241,0.22) 1px, transparent 0); background-size: 22px 22px;"
  ></div>

  <!-- Banner -->
  <a
    href="/signup"
    data-sveltekit-reload
    class="group relative z-10 flex items-center justify-center gap-2 border-b border-primary/10 bg-primary/[0.06] py-2.5 text-[13px] font-medium text-primary transition-colors hover:bg-primary/10"
  >
    <Sparkles class="size-3.5" /> Hopper is live — free starter credits for students
    <ArrowRight class="size-3.5 transition-transform group-hover:translate-x-0.5" />
  </a>

  <!-- Nav -->
  <header class="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
    <a href="/" class="flex items-center gap-2.5">
      <HopperLogo size={32} />
      <span class="text-lg font-bold tracking-tight">Hopper</span>
    </a>
    <nav class="hidden items-center gap-1 rounded-full border border-border bg-card px-1.5 py-1.5 shadow-sm md:flex">
      {#each navLinks as [label, href] (label)}
        <a {href} class="rounded-full px-3.5 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">{label}</a>
      {/each}
    </nav>
    <div class="flex items-center gap-3">
      <a href="/login" class="text-sm font-medium text-foreground transition-colors hover:text-primary">Sign in</a>
      <Button href="/signup" data-sveltekit-reload class="rounded-full">Sign up</Button>
    </div>
  </header>

  <!-- Hero -->
  <section class="relative z-10 mx-auto grid max-w-6xl items-center gap-8 px-6 pb-16 pt-10 lg:grid-cols-[1.05fr_0.95fr] lg:pt-16">
    <!-- glow: violet core with a warm amber rim -->
    <div class="pointer-events-none absolute right-0 top-0 h-[560px] w-[560px] rounded-full opacity-60 blur-3xl" style="background: radial-gradient(closest-side, rgba(196,181,253,0.55), rgba(251,191,36,0.18) 60%, transparent 75%);"></div>

    <div class="relative">
      <span class="hero-reveal inline-flex items-center gap-2 rounded-full border border-border bg-card px-3.5 py-1.5 text-[13px] font-medium text-muted-foreground shadow-sm">
        <Server class="size-3.5 text-primary" /> Self-hosted campus VM cloud
      </span>
      <h1 class="hero-reveal mt-5 text-balance text-5xl font-bold leading-[1.05] tracking-tight sm:text-6xl" style="animation-delay: 80ms">
        Cloud VMs for<br />
        <span class="bg-gradient-to-r from-primary via-violet-500 to-amber-500 bg-clip-text text-transparent">students &amp; teams.</span>
      </h1>
      <p class="hero-reveal mt-5 max-w-md text-lg leading-relaxed text-muted-foreground" style="animation-delay: 160ms">
        Spin up SSH + VS Code virtual machines in seconds. Per-minute credit billing, fair-share scheduling, on your own cluster.
      </p>
      <!-- email-capture pill -->
      <form
        class="hero-reveal mt-8 flex max-w-md items-center gap-1.5 rounded-full border border-border bg-card p-1.5 pl-5 shadow-lg shadow-indigo-950/10 transition-shadow focus-within:shadow-xl focus-within:ring-2 focus-within:ring-primary/25"
        style="animation-delay: 240ms"
        onsubmit={(e) => {
          e.preventDefault();
          startSignup();
        }}
      >
        <input
          type="email"
          bind:value={heroEmail}
          placeholder="What's your university email?"
          aria-label="University email"
          class="min-w-0 flex-1 bg-transparent text-[15px] text-foreground outline-none placeholder:text-muted-foreground"
        />
        <Button type="submit" class="shrink-0 rounded-full px-5">Get started for free</Button>
      </form>
      <p class="hero-reveal mt-3 text-xs text-muted-foreground" style="animation-delay: 300ms">
        Free starter credits · no card required
      </p>
    </div>

    <!-- Floating server racks -->
    <div class="relative hidden h-[420px] lg:block">
      <!-- Rack 1 (taller, right) -->
      <div class="rack-float absolute right-6 top-2 rotate-[-4deg]">
        <div class="absolute -bottom-5 left-1/2 h-16 w-3/4 -translate-x-1/2 rounded-full bg-fuchsia-500/50 blur-2xl"></div>
        <div class="relative w-[168px] rounded-[18px] border-2 border-violet-400/70 bg-gradient-to-br from-[#2a1c4d] to-[#0e0820] p-3.5 shadow-2xl shadow-violet-900/50">
          <div class="mb-2 h-[3px] w-full rounded-full bg-white/15"></div>
          {#each Array(7) as _, i}
            <div class="mb-2 flex items-center gap-1.5 rounded-md bg-white/[0.06] px-2.5 py-2 ring-1 ring-white/10 last:mb-0">
              <span class="size-1.5 rounded-full" style="background:{leds[i % 6]}"></span>
              <span class="size-1.5 rounded-full" style="background:{leds[(i + 2) % 6]}"></span>
              <span class="ml-1 h-[3px] rounded-full bg-white/20" style="width:{barW[i % 7]}px"></span>
            </div>
          {/each}
        </div>
      </div>
      <!-- Rack 2 (shorter, left-lower) -->
      <div class="rack-float absolute left-2 top-[130px] rotate-[5deg]" style="animation-delay: 1.4s">
        <div class="absolute -bottom-5 left-1/2 h-14 w-3/4 -translate-x-1/2 rounded-full bg-fuchsia-500/50 blur-2xl"></div>
        <div class="relative w-[132px] rounded-[18px] border-2 border-violet-400/70 bg-gradient-to-br from-[#2a1c4d] to-[#0e0820] p-3 shadow-2xl shadow-violet-900/50">
          <div class="mb-2 h-[3px] w-full rounded-full bg-white/15"></div>
          {#each Array(6) as _, i}
            <div class="mb-2 flex items-center gap-1.5 rounded-md bg-white/[0.06] px-2.5 py-2 ring-1 ring-white/10 last:mb-0">
              <span class="size-1.5 rounded-full" style="background:{leds[(i + 1) % 6]}"></span>
              <span class="size-1.5 rounded-full" style="background:{leds[(i + 3) % 6]}"></span>
              <span class="ml-1 h-[3px] rounded-full bg-white/20" style="width:{barW[i % 7] - 20}px"></span>
            </div>
          {/each}
        </div>
      </div>
    </div>
  </section>

  <!-- Trusted -->
  <section class="relative z-10 mx-auto flex max-w-6xl flex-col items-center gap-6 px-6 pb-16">
    <p class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Trusted by classrooms and labs at</p>
    <div class="flex flex-wrap items-center justify-center gap-x-10 gap-y-4 text-muted-foreground">
      {#each trusted as o (o.label)}
        <span class="flex items-center gap-2 text-[15px] font-semibold opacity-70 transition-opacity hover:opacity-100">
          <o.icon class="size-4" /> {o.label}
        </span>
      {/each}
    </div>
  </section>

  <!-- Features: alternating chart rows -->
  <section id="features" class="relative z-10 border-y border-border bg-card">
    <div class="mx-auto max-w-6xl px-6 py-16">
      <div class="mx-auto max-w-2xl text-center">
        <span class="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold uppercase tracking-wider text-primary">Features</span>
        <h2 class="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">Compute that keeps the class moving.</h2>
        <p class="mt-3 text-muted-foreground">Autoscaling, fast boots, and zero idle cost — the platform handles the hard parts.</p>
      </div>

      <div class="mt-12 divide-y divide-border">
        <!-- Row 1: Autoscale — wave chart LEFT, text RIGHT -->
        <div class="grid items-center gap-8 py-10 sm:grid-cols-2">
          <div class="relative h-56 rounded-xl">
            <svg viewBox="0 0 380 150" class="h-full w-full">
              <defs><linearGradient id="wg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#a78bfa" stop-opacity="0.35" /><stop offset="1" stop-color="#a78bfa" stop-opacity="0" /></linearGradient></defs>
              <path d="M0 100 C 40 45 80 120 130 70 S 210 20 260 82 S 340 30 380 72 L 380 150 L 0 150 Z" fill="url(#wg)" />
              <path d="M0 100 C 40 45 80 120 130 70 S 210 20 260 82 S 340 30 380 72" fill="none" stroke="#7c3aed" stroke-width="2.5" stroke-linejoin="round" />
            </svg>
            <div class="absolute left-[46%] top-3 rounded-lg bg-slate-900 px-2.5 py-1.5 text-white shadow-lg"><div class="text-[10px] text-slate-400">peak</div><div class="text-xs font-semibold">24 VMs · full class</div></div>
            <div class="absolute bottom-6 left-4 rounded-lg bg-slate-900 px-2.5 py-1.5 text-white shadow-lg"><div class="text-[10px] text-slate-400">off-peak</div><div class="text-xs font-semibold">3 VMs · idle</div></div>
          </div>
          <div class="sm:pl-6">
            <h3 class="text-2xl font-semibold">Autoscale the class</h3>
            <p class="mt-3 leading-relaxed text-muted-foreground">The admission queue starts VMs automatically, in order, as cluster capacity frees up. No manual scheduling.</p>
            <Button href="/signup" data-sveltekit-reload variant="outline" size="sm" class="mt-5 rounded-full">Learn about the queue <ArrowRight class="size-4" /></Button>
          </div>
        </div>

        <!-- Row 2: Fast boots — text LEFT, gantt RIGHT -->
        <div class="grid items-center gap-8 py-10 sm:grid-cols-2">
          <div class="order-2 sm:order-1 sm:pr-6">
            <h3 class="text-2xl font-semibold">Sub-minute boots</h3>
            <p class="mt-3 leading-relaxed text-muted-foreground">VMs boot from pre-built images — Ubuntu, Python, C/C++ or Java — in seconds. Ready before the student finishes typing.</p>
            <Button href="/signup" data-sveltekit-reload variant="outline" size="sm" class="mt-5 rounded-full">See the images <ArrowRight class="size-4" /></Button>
          </div>
          <div class="relative order-1 flex h-56 items-end justify-center gap-2.5 rounded-xl sm:order-2">
            {#each [90, 130, 70, 150, 110, 140, 95, 125] as h, i}
              <div class="w-6 rounded-md" style="height:{h}px; background:{i === 3 ? '#c4b5fd' : 'hsl(var(--muted))'}"></div>
            {/each}
            <div class="absolute right-4 top-4 rounded-lg border border-border bg-card p-3 text-xs shadow-md">
              <div class="mb-1.5 font-semibold">Boot times</div>
              {#each [['#16a34a', 'Running', '4'], ['#94a3b8', 'Booting', '2'], ['#f59e0b', 'Queued', '1']] as [c, l, v]}
                <div class="flex items-center gap-2 py-0.5"><span class="size-2 rounded-sm" style="background:{c}"></span><span class="w-16 text-muted-foreground">{l}</span><span class="font-semibold">{v}</span></div>
              {/each}
            </div>
          </div>
        </div>

        <!-- Row 3: Zero idle — line chart LEFT, text RIGHT -->
        <div class="grid items-center gap-8 py-10 sm:grid-cols-2">
          <div class="relative h-56 rounded-xl">
            <svg viewBox="0 0 380 150" class="h-full w-full">
              <defs><linearGradient id="lg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#a78bfa" stop-opacity="0.3" /><stop offset="1" stop-color="#a78bfa" stop-opacity="0" /></linearGradient></defs>
              <path d="M0 110 L30 70 L60 100 L90 45 L120 88 L150 35 L180 80 L210 60 L240 105 L270 52 L300 92 L330 66 L360 44 L360 150 L0 150 Z" fill="url(#lg)" />
              <path d="M0 110 L30 70 L60 100 L90 45 L120 88 L150 35 L180 80 L210 60 L240 105 L270 52 L300 92 L330 66 L360 44" fill="none" stroke="#7c3aed" stroke-width="2" stroke-linejoin="round" />
            </svg>
          </div>
          <div class="sm:pl-6">
            <h3 class="text-2xl font-semibold">Zero idle cost</h3>
            <p class="mt-3 leading-relaxed text-muted-foreground">Stop a VM and billing stops that second. Credits are charged by the minute — you only pay for real compute.</p>
            <Button href="/credits" variant="outline" size="sm" class="mt-5 rounded-full">How billing works <ArrowRight class="size-4" /></Button>
          </div>
        </div>

        <!-- Row 4: Storage — text LEFT, iso RIGHT -->
        <div class="grid items-center gap-8 py-10 sm:grid-cols-2">
          <div class="order-2 sm:order-1 sm:pr-6">
            <h3 class="text-2xl font-semibold">Persistent storage</h3>
            <p class="mt-3 leading-relaxed text-muted-foreground">Attach fast network volumes to any VM in the cluster. Your files and environment persist across sessions.</p>
            <Button href="/signup" data-sveltekit-reload variant="outline" size="sm" class="mt-5 rounded-full">Learn about volumes <ArrowRight class="size-4" /></Button>
          </div>
          <div class="relative order-1 flex h-56 items-center justify-center sm:order-2">
            <div class="absolute size-40 rounded-full bg-violet-300/30 blur-2xl"></div>
            <svg viewBox="0 0 260 180" class="relative h-full">
              <path d="M130 40 L200 5 L270 40 L200 75 Z M130 40 L200 75 L200 145 M270 40 L200 75 M130 40 L130 110 L200 145 L270 110 L270 40 M130 110 L200 75 L270 110" transform="translate(-40,0)" fill="none" stroke="#c4b5fd" stroke-width="1.5" stroke-linejoin="round" />
              {#each [[196, 66], [130, 96], [196, 112], [130, 66]] as [x, y], i}
                <rect x={x} y={y} width="16" height="16" rx="4" fill={i === 0 ? '#7c3aed' : '#ede9fe'} stroke={i === 0 ? '#7c3aed' : '#cdbff3'} stroke-width="1" />
              {/each}
            </svg>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Flow: timeline + cap cards -->
  <section id="flow" class="relative z-10 mx-auto max-w-6xl scroll-mt-20 px-6 py-20">
    <div class="mx-auto max-w-2xl text-center">
      <h2 class="text-3xl font-bold tracking-tight sm:text-4xl">From plan to running in one flow.</h2>
      <p class="mt-3 text-muted-foreground">One account. No migrations between stages.</p>
      <Button href="/signup" data-sveltekit-reload class="mt-6 rounded-full">Get started <ArrowRight class="size-4" /></Button>
    </div>
    <div class="relative mx-auto mt-14 max-w-4xl">
      <div class="absolute left-0 right-0 top-2 h-0.5 overflow-hidden bg-border">
        <div class="flow-shimmer absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-primary to-transparent"></div>
      </div>
      <div class="grid gap-8 sm:grid-cols-3">
        {#each [
          { t: 'Pick a plan', d: 'Choose Small, Medium or Large — by vCPU and memory — and a base image.' },
          { t: 'Launch & connect', d: 'Boots in seconds. Connect over SSH or open VS Code in the browser.' },
          { t: 'Pay per minute', d: 'Fair-share scheduling moves the class from queue to running fast.' }
        ] as step, i}
          <div class="flow-step relative" style="animation-delay:{i * 120}ms">
            <span class="flow-dot relative z-10 grid size-4 place-items-center rounded-full border-[3px] border-violet-200 bg-primary dark:border-violet-900" style="animation-delay:{i * 300}ms"></span>
            <h3 class="mt-5 text-lg font-semibold">{step.t}</h3>
            <p class="mt-2 text-sm leading-relaxed text-muted-foreground">{step.d}</p>
          </div>
        {/each}
      </div>
    </div>
    <div class="mt-16 grid gap-5 sm:grid-cols-3">
      {#each [
        { icon: ShieldCheck, t: 'High availability', d: 'The orchestrator reschedules VMs on node failure so workloads keep running.' },
        { icon: Boxes, t: 'Managed scheduling', d: 'The queue distributes VMs across nodes — no orchestration to build yourself.' },
        { icon: Radio, t: 'Live metrics & logs', d: 'CPU, memory and logs in real time. An in-browser terminal on every VM.' }
      ] as c, i}
        <div class="flow-step group rounded-2xl border border-border bg-card p-6 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-lg" style="animation-delay:{(i + 3) * 120}ms">
          <div class="grid size-11 place-items-center rounded-xl bg-primary/10 text-primary transition-transform duration-200 group-hover:scale-110"><c.icon class="size-[22px]" strokeWidth={1.75} /></div>
          <h3 class="mt-4 text-lg font-semibold">{c.t}</h3>
          <p class="mt-2 text-sm leading-relaxed text-muted-foreground">{c.d}</p>
          {#if i === 2}
            <svg viewBox="0 0 200 40" class="mt-4 h-9 w-full" preserveAspectRatio="none">
              <polyline class="spark" points="0,30 20,22 40,27 60,13 80,21 100,9 120,19 140,7 160,17 180,5 200,12" fill="none" stroke="hsl(var(--primary))" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          {/if}
        </div>
      {/each}
    </div>
  </section>

  <!-- FAQ -->
  <section id="faq" class="relative z-10 scroll-mt-20 border-t border-border bg-card">
    <div class="mx-auto max-w-3xl px-6 py-20">
      <div class="text-center">
        <h2 class="text-3xl font-bold tracking-tight sm:text-4xl">Questions? Answers.</h2>
        <p class="mt-3 text-muted-foreground">Everything you need to know about running on Hopper.</p>
      </div>
      <div class="mt-10 space-y-3">
        {#each faqs as f, i}
          <div class={`rounded-xl border transition-colors ${openFaq === i ? 'border-primary/30 bg-primary/[0.03]' : 'border-border bg-background'}`}>
            <button type="button" onclick={() => (openFaq = openFaq === i ? -1 : i)} class="flex w-full items-center justify-between gap-4 px-5 py-4 text-left">
              <span class="text-[15px] font-medium">{f.q}</span>
              {#if openFaq === i}<Minus class="size-4 shrink-0 text-primary" />{:else}<Plus class="size-4 shrink-0 text-primary" />{/if}
            </button>
            {#if openFaq === i}
              <p class="px-5 pb-4 text-sm leading-relaxed text-muted-foreground">{f.a}</p>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  </section>

  <!-- CTA -->
  <section class="relative z-10 mx-auto max-w-3xl px-6 py-24 text-center">
    <div class="pointer-events-none absolute left-1/2 top-8 h-64 w-96 -translate-x-1/2 rounded-full opacity-50 blur-3xl" style="background: radial-gradient(closest-side, rgba(196,181,253,0.5), transparent 70%);"></div>
    <div class="relative mx-auto grid size-16 place-items-center rounded-2xl bg-gradient-to-br from-primary to-violet-500 text-white shadow-lg shadow-primary/30">
      <HopperLogo size={48} class="!shadow-none" />
    </div>
    <h2 class="relative mt-6 text-3xl font-bold tracking-tight sm:text-4xl">Ready to launch your first VM?</h2>
    <p class="relative mx-auto mt-3 max-w-lg text-muted-foreground">Sign up with your university email. Free credits to get you started — no card required.</p>
    <div class="relative mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
      <Button href="/signup" data-sveltekit-reload size="lg" class="h-12 rounded-full px-6 text-[15px]">Get started</Button>
      <Button href="/login" variant="outline" size="lg" class="h-12 rounded-full px-6 text-[15px]">Sign in</Button>
    </div>
  </section>

  <!-- Footer -->
  <footer class="relative z-10 border-t border-border bg-card/50">
    <div class="mx-auto grid max-w-6xl gap-10 px-6 py-12 sm:grid-cols-[1.4fr_1fr_1fr]">
      <div>
        <div class="flex items-center gap-2.5">
          <HopperLogo size={28} />
          <span class="text-base font-bold text-foreground">Hopper</span>
        </div>
        <p class="mt-3 max-w-xs text-sm leading-relaxed text-muted-foreground">
          A self-hosted cloud VM platform for classrooms and labs. SSH + VS Code in seconds, billed by the minute.
        </p>
      </div>
      <nav aria-label="Product">
        <h4 class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Product</h4>
        <ul class="mt-3 space-y-2 text-sm">
          <li><a href="#features" class="text-muted-foreground transition-colors hover:text-foreground">Features</a></li>
          <li><a href="#flow" class="text-muted-foreground transition-colors hover:text-foreground">How it works</a></li>
          <li><a href="#faq" class="text-muted-foreground transition-colors hover:text-foreground">FAQ</a></li>
        </ul>
      </nav>
      <nav aria-label="Account">
        <h4 class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Account</h4>
        <ul class="mt-3 space-y-2 text-sm">
          <li><a href="/signup" data-sveltekit-reload class="text-muted-foreground transition-colors hover:text-foreground">Create account</a></li>
          <li><a href="/login" class="text-muted-foreground transition-colors hover:text-foreground">Sign in</a></li>
          <li><a href="/forgot-password" class="text-muted-foreground transition-colors hover:text-foreground">Reset password</a></li>
        </ul>
      </nav>
    </div>
    <div class="border-t border-border/60">
      <p class="mx-auto max-w-6xl px-6 py-5 text-center text-xs text-muted-foreground sm:text-left">
        © 2026 Hopper · Self-hosted on Kubernetes · Secured by Keycloak
      </p>
    </div>
  </footer>
</div>

<style>
  @keyframes flowShimmer {
    0% { transform: translateX(-120%); }
    100% { transform: translateX(360%); }
  }
  .flow-shimmer { animation: flowShimmer 2.8s ease-in-out infinite; }

  @keyframes dotPulse {
    0%, 100% { box-shadow: 0 0 0 0 hsl(var(--primary) / 0.5); }
    60% { box-shadow: 0 0 0 7px hsl(var(--primary) / 0); }
  }
  .flow-dot { animation: dotPulse 2.4s ease-in-out infinite; }

  @keyframes flowFadeUp {
    from { opacity: 0; transform: translateY(14px); }
    to { opacity: 1; transform: none; }
  }
  .flow-step { animation: flowFadeUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both; }

  @keyframes sparkDraw {
    from { stroke-dashoffset: 260; }
    to { stroke-dashoffset: 0; }
  }
  .spark {
    stroke-dasharray: 260;
    animation: sparkDraw 1.8s ease-out forwards;
  }

  @keyframes heroReveal {
    from { opacity: 0; transform: translateY(16px); }
    to { opacity: 1; transform: none; }
  }
  .hero-reveal { animation: heroReveal 0.7s cubic-bezier(0.16, 1, 0.3, 1) both; }

  @keyframes rackFloat {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-10px); }
  }
  .rack-float { animation: rackFloat 6s ease-in-out infinite; }

  @media (prefers-reduced-motion: reduce) {
    .flow-shimmer, .flow-dot, .flow-step, .spark, .hero-reveal, .rack-float { animation: none !important; }
  }
</style>
