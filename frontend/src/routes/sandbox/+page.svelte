<script lang="ts">
  import {
    Sparkles,
    Wand2,
    Check,
    Cpu,
    MemoryStick,
    HardDrive,
    Coins,
    Rocket,
    AlertTriangle,
    Package,
    Boxes,
    Database,
    Puzzle,
    Terminal,
    Info,
    ChevronDown,
    RefreshCw
  } from 'lucide-svelte';
  import { goto } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import { VM_PLAN_INFO, type VmPlan } from '$lib/types';
  import { api, ApiError } from '$lib/api/client';
  import {
    Button,
    Card,
    CardHeader,
    CardTitle,
    CardDescription,
    CardContent,
    Textarea,
    Badge,
    Separator
  } from '$lib/ui';
  import PageTitle from '$lib/components/PageTitle.svelte';
  import { cn, copyToClipboard } from '$lib/utils';

  let { data }: { data: { balance: number } } = $props();

  type WorkspaceSpec = {
    summary: string;
    base_template: string;
    apt_packages: string[];
    pip_packages: string[];
    npm_packages: string[];
    vscode_extensions: string[];
    services: string[];
  };
  type RejectedItem = { kind: string; value: string; reason: string };
  type PlanResponse = {
    spec: WorkspaceSpec;
    plan: VmPlan;
    credits_per_hour: number;
    provision_script: string;
    rejected: RejectedItem[];
    llm_used: boolean;
    notes: string[];
  };
  type ProvisionResponse = { pod_id: string; state: string };

  const EXAMPLES = [
    'React frontend with a FastAPI backend and a Postgres database',
    'PyTorch project for training an image classifier, with Jupyter',
    'C++ competitive-programming setup with CMake and GDB',
    'Spring Boot REST API using Maven and MySQL'
  ];

  let description = $state('');
  let selectedPlan = $state<VmPlan>('small');
  let planning = $state(false);
  let provisioning = $state(false);
  let plan = $state<PlanResponse | null>(null);
  let scriptOpen = $state(false);

  const planRate = $derived(VM_PLAN_INFO[selectedPlan].rate);
  // Once a plan is proposed the authoritative hourly rate comes from the server.
  const hourlyRate = $derived(plan?.credits_per_hour ?? planRate);
  const canAfford = $derived(data.balance >= hourlyRate);
  const canGenerate = $derived(description.trim().length >= 3 && !planning);

  const specGroups = $derived.by(() => {
    if (!plan) return [];
    const s = plan.spec;
    return [
      { label: 'APT packages', items: s.apt_packages, icon: Package },
      { label: 'Python (pip)', items: s.pip_packages, icon: Boxes },
      { label: 'Node (npm)', items: s.npm_packages, icon: Boxes },
      { label: 'VS Code extensions', items: s.vscode_extensions, icon: Puzzle },
      { label: 'Services', items: s.services, icon: Database }
    ].filter((g) => g.items.length > 0);
  });

  async function generate() {
    if (!canGenerate) return;
    planning = true;
    plan = null;
    scriptOpen = false;
    const id = toast.loading('Designing your workspace…');
    try {
      plan = await api.post<PlanResponse>('/sandbox/plan', {
        description: description.trim(),
        plan: selectedPlan
      });
      toast.success(plan.llm_used ? 'Workspace planned by AI' : 'Workspace planned', {
        id,
        description: plan.llm_used
          ? 'Review the proposed setup, then launch.'
          : 'Built with the keyword planner (no LLM key set).'
      });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Could not plan the workspace';
      toast.error('Planning failed', { id, description: msg });
    } finally {
      planning = false;
    }
  }

  async function launch() {
    if (!plan || provisioning) return;
    if (!canAfford) {
      toast.error(
        `You need at least ${hourlyRate} credit${hourlyRate === 1 ? '' : 's'} to launch this VM`,
        { description: `Current balance: ${data.balance.toFixed(2)} credits.` }
      );
      return;
    }
    provisioning = true;
    const id = toast.loading('Launching your sandbox…');
    try {
      const res = await api.post<ProvisionResponse>('/sandbox/provision', {
        spec: plan.spec,
        plan: plan.plan,
        description: description.trim()
      });
      toast.success('Sandbox launched', {
        id,
        description: 'Provisioning your tools on first boot — opening the VM…'
      });
      await goto(`/pods/${res.pod_id}`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Could not launch the sandbox';
      toast.error('Launch failed', { id, description: msg });
      provisioning = false;
    }
  }

  async function copyScript() {
    if (!plan) return;
    try {
      await copyToClipboard(plan.provision_script);
      toast.success('provision.sh copied');
    } catch {
      toast.error('Could not access clipboard');
    }
  }
</script>

<div class="space-y-6">
  <PageTitle
    title="Smart Sandbox"
    description="Describe your project in plain English — we design a ready-to-code VM with the right tools, then you launch it."
  />

  <!-- Prompt panel -->
  <Card class="animate-fade-up surface-glow overflow-hidden">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <span
          class="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-info text-primary-foreground shadow-sm"
        >
          <Sparkles class="size-4" />
        </span>
        Describe your project
      </CardTitle>
      <CardDescription>
        Mention the language, frameworks, and any database you need. The more
        specific you are, the better the setup.
      </CardDescription>
    </CardHeader>
    <Separator />
    <CardContent class="space-y-5 pt-6">
      <div>
        <Textarea
          bind:value={description}
          rows={4}
          maxlength={2000}
          placeholder="e.g. A React frontend with a FastAPI backend and a Postgres database"
          disabled={planning || provisioning}
          onkeydown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') generate();
          }}
        />
        <div class="mt-2 flex flex-wrap items-center gap-1.5">
          <span class="text-xs text-muted-foreground">Try:</span>
          {#each EXAMPLES as ex (ex)}
            <button
              type="button"
              class="rounded-full border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
              onclick={() => (description = ex)}
              disabled={planning || provisioning}
            >
              {ex}
            </button>
          {/each}
        </div>
      </div>

      <!-- Plan picker -->
      <div>
        <h3 class="mb-3 text-sm font-semibold">Resource plan</h3>
        <div class="grid gap-3 sm:grid-cols-3">
          {#each Object.entries(VM_PLAN_INFO) as [p, info] (p)}
            <button
              type="button"
              class={cn(
                'group relative flex flex-col rounded-xl border p-3.5 text-left transition-all hover:border-primary/50 hover:shadow-sm',
                selectedPlan === p
                  ? 'border-primary bg-primary/[0.04] ring-2 ring-primary/25'
                  : 'border-border bg-card'
              )}
              onclick={() => (selectedPlan = p as VmPlan)}
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="text-sm font-semibold capitalize">{p}</div>
                  <p class="mt-0.5 text-xs leading-snug text-muted-foreground">
                    {info.description}
                  </p>
                </div>
                <div
                  class={cn(
                    'flex size-5 shrink-0 items-center justify-center rounded-full border transition-colors',
                    selectedPlan === p
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border bg-card group-hover:border-primary/40'
                  )}
                >
                  {#if selectedPlan === p}<Check class="size-3" />{/if}
                </div>
              </div>
              <div
                class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs font-medium"
              >
                <span class="inline-flex items-center gap-1.5">
                  <Cpu class="size-3.5 text-primary" />{info.cpu}
                </span>
                <span class="inline-flex items-center gap-1.5">
                  <MemoryStick class="size-3.5 text-info" />{info.memory}
                </span>
                <span class="inline-flex items-center gap-1.5">
                  <HardDrive class="size-3.5 text-success" />{info.disk}
                </span>
              </div>
              <div
                class="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-primary"
              >
                <Coins class="size-3.5" />{info.rate} credit{info.rate === 1 ? '' : 's'}<span
                  class="font-normal text-muted-foreground">/hr</span
                >
              </div>
            </button>
          {/each}
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <Button onclick={generate} disabled={!canGenerate}>
          <Wand2 class="size-4" />
          {planning ? 'Designing…' : plan ? 'Re-generate' : 'Design workspace'}
        </Button>
        <span class="text-xs text-muted-foreground">
          Nothing is created or billed until you launch.
        </span>
      </div>
    </CardContent>
  </Card>

  <!-- Proposed workspace -->
  {#if plan}
    <Card class="animate-fade-up overflow-hidden">
      <CardHeader>
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle class="flex items-center gap-2">
              <Boxes class="size-5 text-primary" />
              Proposed workspace
            </CardTitle>
            <CardDescription class="mt-1">{plan.spec.summary}</CardDescription>
          </div>
          <Badge variant={plan.llm_used ? 'default' : 'secondary'}>
            <Sparkles class="mr-1 size-3" />
            {plan.llm_used ? 'AI-planned' : 'Keyword planner'}
          </Badge>
        </div>
      </CardHeader>
      <Separator />
      <CardContent class="space-y-5 pt-6">
        <!-- Base image + rate -->
        <div class="flex flex-wrap items-center gap-4 text-sm">
          <span class="inline-flex items-center gap-1.5">
            <HardDrive class="size-4 text-muted-foreground" />
            Base image:
            <span class="font-semibold">{plan.spec.base_template}</span>
          </span>
          <span class="inline-flex items-center gap-1.5">
            <Coins class="size-4 text-primary" />
            <span class="font-semibold text-primary">{hourlyRate}</span>
            credit{hourlyRate === 1 ? '' : 's'}/hr
          </span>
        </div>

        {#if plan.notes.length}
          <div
            class="flex items-start gap-2 rounded-lg border border-info/30 bg-info/5 p-3 text-sm text-muted-foreground"
          >
            <Info class="mt-0.5 size-4 shrink-0 text-info" />
            <div class="space-y-0.5">
              {#each plan.notes as note (note)}<p>{note}</p>{/each}
            </div>
          </div>
        {/if}

        <!-- Package groups -->
        {#if specGroups.length}
          <div class="grid gap-4 sm:grid-cols-2">
            {#each specGroups as group (group.label)}
              <div>
                <h4
                  class="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                >
                  <group.icon class="size-3.5" />{group.label}
                </h4>
                <div class="flex flex-wrap gap-1.5">
                  {#each group.items as item (item)}
                    <Badge variant="secondary" class="font-mono text-[11px]">{item}</Badge>
                  {/each}
                </div>
              </div>
            {/each}
          </div>
        {:else}
          <p class="text-sm text-muted-foreground">
            A clean {plan.spec.base_template} box — no extra packages needed.
          </p>
        {/if}

        <!-- Rejected items -->
        {#if plan.rejected.length}
          <div
            class="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 p-3 text-sm"
          >
            <AlertTriangle class="mt-0.5 size-4 shrink-0 text-warning" />
            <div>
              <p class="font-medium">
                {plan.rejected.length} item{plan.rejected.length === 1 ? '' : 's'} dropped
                (not on the authorized allowlist):
              </p>
              <ul class="mt-1 space-y-0.5 text-muted-foreground">
                {#each plan.rejected as r (r.kind + r.value)}
                  <li>
                    <span class="font-mono text-xs">{r.value}</span>
                    <span class="text-xs">({r.kind}) — {r.reason}</span>
                  </li>
                {/each}
              </ul>
            </div>
          </div>
        {/if}

        <!-- provision.sh -->
        <div class="rounded-lg border border-border">
          <button
            type="button"
            class="flex w-full items-center justify-between px-3 py-2.5 text-sm font-medium"
            onclick={() => (scriptOpen = !scriptOpen)}
          >
            <span class="inline-flex items-center gap-1.5">
              <Terminal class="size-4 text-muted-foreground" />
              View provision.sh
            </span>
            <ChevronDown
              class={cn('size-4 transition-transform', scriptOpen && 'rotate-180')}
            />
          </button>
          {#if scriptOpen}
            <Separator />
            <div class="relative">
              <Button
                variant="ghost"
                size="sm"
                class="absolute right-2 top-2"
                onclick={copyScript}
              >
                Copy
              </Button>
              <pre
                class="max-h-80 overflow-auto rounded-b-lg bg-muted/50 p-3 text-xs leading-relaxed"><code
                  >{plan.provision_script}</code
                ></pre>
            </div>
          {/if}
        </div>

        <!-- Launch -->
        <div class="flex flex-wrap items-center gap-3 pt-1">
          <Button onclick={launch} disabled={provisioning || !canAfford}>
            <Rocket class="size-4" />
            {provisioning ? 'Launching…' : 'Approve & launch'}
          </Button>
          <Button variant="outline" onclick={generate} disabled={planning || provisioning}>
            <RefreshCw class="size-4" />
            Re-generate
          </Button>
          {#if !canAfford}
            <span class="inline-flex items-center gap-1.5 text-sm text-warning">
              <AlertTriangle class="size-4" />
              Insufficient credits (balance {data.balance.toFixed(2)}).
            </span>
          {/if}
        </div>
      </CardContent>
    </Card>
  {/if}
</div>
