<script lang="ts">
  import { onMount } from 'svelte';
  import {
    Square,
    ArrowLeft,
    Terminal as TerminalIcon,
    FileUp,
    Info,
    Plus,
    X,
    Eye,
    EyeOff,
    Copy,
    ExternalLink,
    Code2,
    MessageSquareWarning,
    Server,
    Coins,
    KeyRound
  } from 'lucide-svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { invalidateAll, goto } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import CpuMetrics from '$lib/components/CpuMetrics.svelte';
  import Terminal from '$lib/components/Terminal.svelte';
  import PodUsage from '$lib/components/PodUsage.svelte';
  import PodFiles from '$lib/components/PodFiles.svelte';
  import { api, ApiError } from '$lib/api/client';
  import { confirm } from '$lib/confirm.svelte';
  import { cn, copyToClipboard, relTime, shortId } from '$lib/utils';
  import {
    Button,
    Card,
    CardContent,
    Badge,
    Tabs,
    Tooltip,
    Dialog,
    Textarea
  } from '$lib/ui';
  import { VM_PLAN_INFO } from '$lib/types';
  import type { Pod, User, VmMetrics, VmPlan } from '$lib/types';

  let {
    data
  }: {
    data: { pod: Pod | null; nodeIp: string; user: User | null };
  } = $props();

  // Plan sheet drives Specs (disk) + Billing (rate) from the pod's plan.
  const planInfo = $derived(VM_PLAN_INFO[data.pod?.plan as VmPlan]);
  const planRate = $derived(planInfo?.rate ?? 0);
  const uptimeMs = $derived(
    data.pod && data.pod.state === 'running'
      ? Date.now() - new Date(data.pod.created_at).getTime()
      : 0
  );
  const uptimeLabel = $derived.by(() => {
    const m = Math.floor(uptimeMs / 60000);
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ${m % 60}m`;
    return `${Math.floor(h / 24)}d ${h % 24}h`;
  });
  const sessionCost = $derived((uptimeMs / 3600000) * planRate);

  let metrics = $state<VmMetrics | null>(null);

  let activeTab = $state('overview');
  let showPassword = $state(false);
  let hydrated = $state(false);

  onMount(() => {
    const requestedTab = new URLSearchParams(window.location.search).get('tab');
    if (requestedTab === 'overview' || requestedTab === 'terminal' || requestedTab === 'files') {
      activeTab = requestedTab;
    }
    hydrated = true;
  });

  // Terminal sessions management
  let terminalSessions = $state([{ id: 'term-1' }]);
  let activeTerminalId = $state('term-1');

  function addTerminal() {
    const id = `term-${Date.now()}`;
    terminalSessions = [...terminalSessions, { id }];
    activeTerminalId = id;
  }

  function removeTerminal(id: string) {
    terminalSessions = terminalSessions.filter((t) => t.id !== id);
    if (activeTerminalId === id && terminalSessions.length > 0) {
      activeTerminalId = terminalSessions[terminalSessions.length - 1].id;
    }
    if (terminalSessions.length === 0) addTerminal();
  }

  // Live metrics SSE — preserved from prior implementation.
  $effect(() => {
    if (data.pod?.state !== 'running') return;
    const podId = data.pod.id;
    let cancelled = false;

    const es = new EventSource(`/api/pods/${podId}/metrics`);
    es.addEventListener('metrics', (e) => {
      if (cancelled) return;
      try {
        metrics = JSON.parse(e.data);
      } catch {}
    });

    return () => {
      cancelled = true;
      es.close();
    };
  });

  // --- Report Issue dialog ---
  let issueOpen = $state(false);
  let issueText = $state('');
  let issueSubmitting = $state(false);
  async function submitIssue() {
    if (!data.pod) return;
    const description = issueText.trim();
    if (description.length < 5) {
      toast.error('Please describe the issue (at least 5 characters).');
      return;
    }
    issueSubmitting = true;
    const tid = toast.loading('Sending report…');
    try {
      await api.post('/issues/', { pod_id: data.pod.id, description });
      toast.success('Report sent', {
        id: tid,
        description: 'An admin will take a look. Thanks for flagging it.'
      });
      issueText = '';
      issueOpen = false;
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Failed to send report';
      toast.error('Could not send report', { id: tid, description: msg });
    } finally {
      issueSubmitting = false;
    }
  }

  async function terminatePod() {
    if (!data.pod) return;
    const ok = await confirm({
      title: `Terminate VM ${shortId(data.pod.id)}?`,
      description:
        'This will permanently stop the container, drop unsaved changes, and stop billing. This cannot be undone.',
      confirmLabel: 'Terminate',
      variant: 'destructive'
    });
    if (!ok) return;

    const id = toast.loading('Terminating VM…');
    try {
      await api.delete(`/pods/${data.pod.id}`);
      toast.success('VM terminated', { id });
      await invalidateAll();
      goto('/pods');
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Failed to terminate VM';
      toast.error('Termination failed', { id, description: msg });
    }
  }

  // Launcher page: polls code-server readiness behind a branded splash, then
  // swaps the tab for the editor — no raw 503s during cold start.
  function vscodeUrl(p: Pod): string {
    return `/pods/${p.id}/vscode`;
  }

  async function copyText(text: string, label = 'Copied') {
    try {
      await copyToClipboard(text);
      toast.success(label);
    } catch {
      toast.error('Could not access clipboard');
    }
  }

  const stateBadge: Record<
    string,
    { variant: 'success' | 'warning' | 'info' | 'destructive' | 'muted'; label: string; pulse?: boolean }
  > = {
    running: { variant: 'success', label: 'Running' },
    pending: { variant: 'warning', label: 'Pending', pulse: true },
    creating: { variant: 'info', label: 'Creating', pulse: true },
    stopping: { variant: 'warning', label: 'Stopping', pulse: true },
    terminated: { variant: 'muted', label: 'Terminated' },
    failed: { variant: 'destructive', label: 'Failed' }
  };
</script>

{#if data.pod}
  {@const pod = data.pod}
  {@const podState = data.pod.state}
  {@const cfg = stateBadge[podState] ?? stateBadge.terminated}
  {@const isRunning = podState === 'running'}
  {@const canTerminate = !['terminated', 'failed'].includes(podState)}

  <div
    data-pod-hydrated={hydrated}
    class={cn(
      'flex flex-col',
      activeTab === 'terminal' && 'h-[calc(100vh-7rem)]'
    )}
  >
    <!-- Header -->
    <div class="mb-5 shrink-0">
      <a
        href="/pods"
        class="group mb-3 inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft class="size-4 transition-transform group-hover:-translate-x-0.5" />
        Back to VMs
      </a>
      <Card class="flex flex-col items-start justify-between gap-4 p-5 sm:flex-row sm:items-center">
        <div class="flex min-w-0 items-center gap-4">
          <span class="grid size-12 shrink-0 place-items-center rounded-xl bg-muted text-foreground">
            <Server class="size-6" />
          </span>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2.5">
              <h1 class="truncate font-mono text-xl font-bold tracking-tight sm:text-2xl">
                {shortId(data.pod.id, 12)}
              </h1>
              <Badge variant={cfg.variant}>
                {#if cfg.pulse}<Spinner class="size-3" />{/if}
                {cfg.label}
              </Badge>
            </div>
            <p class="mt-1 truncate text-sm text-muted-foreground">
              <span class="capitalize">{data.pod.plan}</span> · {data.pod.image} · created {relTime(data.pod.created_at)}
            </p>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          {#if isRunning && pod.vscode_port}
            <Button variant="outline" href={vscodeUrl(pod)} target="_blank" rel="noopener noreferrer">
              <Code2 class="size-4" /> Open VS Code
              <ExternalLink class="size-3 opacity-60" />
            </Button>
          {/if}
          {#if isRunning}
            <Button variant="outline" onclick={() => (issueOpen = true)}>
              <MessageSquareWarning class="size-4" /> Report issue
            </Button>
          {/if}
          {#if canTerminate}
            <Button variant="destructive" onclick={terminatePod}>
              <Square class="size-4" /> Terminate
            </Button>
          {/if}
        </div>
      </Card>
    </div>

    <!-- Tabs -->
    <div class="flex min-h-0 flex-1 flex-col">
      <div
        class="mb-4 mt-1 inline-flex h-9 self-start items-center justify-center gap-1 rounded-full border border-border/60 bg-muted/60 p-1 text-muted-foreground backdrop-blur-sm"
        role="tablist"
        aria-label="Pod detail sections"
      >
        <button
          id="pod-tab-overview"
          type="button"
          role="tab"
          aria-selected={activeTab === 'overview'}
          aria-controls="pod-panel-overview"
          class={cn(
            'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1 text-sm font-medium transition-all duration-200',
            'ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            activeTab === 'overview'
              ? 'bg-card text-foreground shadow-sm ring-1 ring-border/50'
              : 'text-muted-foreground hover:text-foreground'
          )}
          onclick={() => (activeTab = 'overview')}
        >
          <Info class="size-3.5" /> Overview
        </button>
        <button
          id="pod-tab-terminal"
          type="button"
          role="tab"
          aria-selected={activeTab === 'terminal'}
          aria-controls="pod-panel-terminal"
          class={cn(
            'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1 text-sm font-medium transition-all duration-200',
            'ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            activeTab === 'terminal'
              ? 'bg-card text-foreground shadow-sm ring-1 ring-border/50'
              : 'text-muted-foreground hover:text-foreground'
          )}
          onclick={() => (activeTab = 'terminal')}
        >
          <TerminalIcon class="size-3.5" /> Terminal
        </button>
        <button
          id="pod-tab-files"
          type="button"
          role="tab"
          aria-selected={activeTab === 'files'}
          aria-controls="pod-panel-files"
          class={cn(
            'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1 text-sm font-medium transition-all duration-200',
            'ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            activeTab === 'files'
              ? 'bg-card text-foreground shadow-sm ring-1 ring-border/50'
              : 'text-muted-foreground hover:text-foreground'
          )}
          onclick={() => (activeTab = 'files')}
        >
          <FileUp class="size-3.5" /> Files
        </button>
      </div>

      <!-- Terminal -->
      {#if activeTab === 'terminal'}
        <div id="pod-panel-terminal" role="tabpanel" aria-labelledby="pod-tab-terminal" class="min-h-0 flex-1">
        <div
          class="flex h-full flex-col overflow-hidden rounded-xl border border-border bg-card terminal-frame"
        >
          <div class="flex items-center border-b border-border bg-muted/30">
            <div class="flex flex-1 overflow-x-auto">
              {#each terminalSessions as session, idx (session.id)}
                <div
                  class={`flex min-w-[10rem] items-center border-r border-border transition-colors ${
                    activeTerminalId === session.id
                      ? 'bg-card'
                      : 'hover:bg-muted/60'
                  }`}
                >
                  <button
                    class={`flex flex-1 items-center gap-2 px-3 py-2 text-xs ${
                      activeTerminalId === session.id
                        ? 'font-medium text-foreground'
                        : 'text-muted-foreground'
                    }`}
                    onclick={() => (activeTerminalId = session.id)}
                  >
                    <TerminalIcon class="size-3.5" />
                    Terminal {idx + 1}
                  </button>
                  <button
                    class="mr-1 rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    onclick={() => removeTerminal(session.id)}
                    title="Close terminal"
                    aria-label="Close terminal"
                  >
                    <X class="size-3.5" />
                  </button>
                </div>
              {/each}
            </div>
            <button
              type="button"
              class="px-3 py-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onclick={addTerminal}
              aria-label="New terminal"
              title="New terminal"
            >
              <Plus class="size-4" />
            </button>
          </div>
          <div class="relative min-h-0 flex-1 bg-black">
            {#if !isRunning}
              <div
                class="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-black/85 text-center text-white"
              >
                <TerminalIcon class="size-10 opacity-50" />
                <p class="text-sm">
                  VM is <span class="font-medium">{podState}</span>. Terminal access
                  is only available when the VM is running.
                </p>
              </div>
            {/if}
            {#if isRunning}
              {#each terminalSessions as session (session.id)}
                <div
                  class={`absolute inset-0 ${
                    activeTerminalId === session.id
                      ? 'z-10 opacity-100'
                      : 'pointer-events-none z-0 opacity-0'
                  }`}
                >
                  <Terminal
                    podId={data.pod.id}
                    sessionId={session.id}
                    isActive={activeTerminalId === session.id}
                  />
                </div>
              {/each}
            {/if}
          </div>
        </div>
        </div>
      {/if}

      <!-- Files -->
      {#if activeTab === 'files'}
        <div id="pod-panel-files" role="tabpanel" aria-labelledby="pod-tab-files" class="min-h-0 flex-1 overflow-y-auto">
        <PodFiles podId={data.pod.id} podRunning={isRunning} />
        </div>
      {/if}

      <!-- Overview -->
      {#if activeTab === 'overview'}
        <div id="pod-panel-overview" role="tabpanel" aria-labelledby="pod-tab-overview" class="min-h-0 flex-1 overflow-y-auto">
        <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
          <!-- LEFT: specifications + live metrics -->
          <div class="space-y-4">
            <Card class="overflow-hidden">
              <div class="flex items-center gap-2.5 px-5 pb-4 pt-5">
                <span class="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Server class="size-4" />
                </span>
                <h3 class="text-sm font-semibold">Specifications</h3>
              </div>
              <dl class="grid grid-cols-2 gap-px border-t border-border/60 bg-border/60 sm:grid-cols-3">
                <div class="bg-card px-5 py-3.5">
                  <dt class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">vCPU</dt>
                  <dd class="mt-1 text-sm font-medium">{data.pod.cpu ?? planInfo?.cpu ?? '—'}</dd>
                </div>
                <div class="bg-card px-5 py-3.5">
                  <dt class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Memory</dt>
                  <dd class="mt-1 text-sm font-medium">{data.pod.memory ?? planInfo?.memory ?? '—'}</dd>
                </div>
                <div class="bg-card px-5 py-3.5">
                  <dt class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Disk</dt>
                  <dd class="mt-1 text-sm font-medium">{planInfo?.disk ?? '—'}</dd>
                </div>
                <div class="bg-card px-5 py-3.5">
                  <dt class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Plan</dt>
                  <dd class="mt-1 text-sm font-medium capitalize">{data.pod.plan}</dd>
                </div>
                <div class="bg-card px-5 py-3.5">
                  <dt class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Namespace</dt>
                  <dd class="mt-1 truncate font-mono text-xs">{data.pod.namespace}</dd>
                </div>
                <div class="bg-card px-5 py-3.5">
                  <dt class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Node</dt>
                  <dd class="mt-1 truncate font-mono text-xs">{data.pod.node_name ?? '—'}</dd>
                </div>
                <div class="col-span-2 bg-card px-5 py-3.5 sm:col-span-3">
                  <dt class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Image</dt>
                  <dd class="mt-1 truncate font-mono text-xs">{data.pod.image}</dd>
                </div>
                <div class="col-span-2 bg-card px-5 py-3.5 sm:col-span-3">
                  <dt class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Created</dt>
                  <dd class="mt-1 text-sm">{new Date(data.pod.created_at).toLocaleString()}</dd>
                </div>
              </dl>
            </Card>

            {#if isRunning}
              <CpuMetrics {metrics} />
            {:else}
              <Card class="border-dashed">
                <CardContent class="py-10 text-center text-sm text-muted-foreground">
                  Live metrics are only available when the VM is running.
                </CardContent>
              </Card>
            {/if}
          </div>

          <!-- RIGHT: access + billing -->
          <div class="space-y-4">
            <Card class="overflow-hidden">
              <div class="flex items-center gap-2.5 px-5 pb-4 pt-5">
                <span class="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <KeyRound class="size-4" />
                </span>
                <h3 class="text-sm font-semibold">Access</h3>
              </div>

              {#if isRunning && data.pod.ssh_port}
                <div class="space-y-3 border-t border-border/60 px-5 py-5">
                  <div class="space-y-1.5">
                    <div class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      SSH command
                    </div>
                    <div class="relative">
                      <TerminalIcon class="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
                      <code
                        class="block w-full select-all overflow-x-auto whitespace-nowrap rounded-lg bg-[#0f172a] py-2.5 pl-9 pr-11 font-mono text-xs text-slate-100"
                      >
                        ssh root@{data.nodeIp} -p {data.pod.ssh_port}
                      </code>
                      <button
                        class="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-300 transition-colors hover:bg-white/10 hover:text-white"
                        title="Copy command"
                        aria-label="Copy SSH command"
                        onclick={() =>
                          copyText(`ssh root@${data.nodeIp} -p ${data.pod!.ssh_port}`, 'SSH command copied')}
                      >
                        <Copy class="size-3.5" />
                      </button>
                    </div>
                  </div>

                  {#if data.pod.vscode_port}
                    <Button variant="secondary" class="w-full" href={vscodeUrl(data.pod)} target="_blank" rel="noopener noreferrer">
                      <Code2 class="size-4" /> Open in VS Code
                      <ExternalLink class="ml-auto size-3 opacity-60" />
                    </Button>
                  {/if}
                </div>

                <dl class="divide-y divide-border/60 border-t border-border/60">
                  <div class="flex items-center justify-between px-5 py-3">
                    <dt class="text-sm text-muted-foreground">Username</dt>
                    <dd class="font-mono text-sm font-medium">root</dd>
                  </div>
                  {#if data.pod.ssh_password}
                    <div class="flex items-center justify-between gap-2 px-5 py-3">
                      <dt class="text-sm text-muted-foreground">Password</dt>
                      <dd class="flex items-center gap-1">
                        <span class="font-mono text-sm font-medium {showPassword ? '' : 'tracking-widest'}">
                          {showPassword ? data.pod.ssh_password : '•'.repeat(Math.min(12, data.pod.ssh_password.length))}
                        </span>
                        <button
                          class="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                          title={showPassword ? 'Hide' : 'Reveal'}
                          aria-label={showPassword ? 'Hide password' : 'Reveal password'}
                          onclick={() => (showPassword = !showPassword)}
                        >
                          {#if showPassword}<EyeOff class="size-3.5" />{:else}<Eye class="size-3.5" />{/if}
                        </button>
                        <button
                          class="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                          title="Copy password"
                          aria-label="Copy password"
                          onclick={() => copyText(data.pod!.ssh_password ?? '', 'Password copied')}
                        >
                          <Copy class="size-3.5" />
                        </button>
                      </dd>
                    </div>
                  {/if}
                  <div class="flex items-center justify-between px-5 py-3">
                    <dt class="text-sm text-muted-foreground">SSH port</dt>
                    <dd class="font-mono text-sm font-medium tabular-nums">{data.pod.ssh_port}</dd>
                  </div>
                </dl>
              {:else}
                <div class="border-t border-border/60 px-5 py-8 text-center text-sm text-muted-foreground">
                  SSH access is available when the VM is running.
                </div>
              {/if}

              <div class="flex items-start gap-2 border-t border-border/60 bg-muted/30 px-5 py-3 text-xs text-muted-foreground">
                <KeyRound class="mt-0.5 size-3.5 shrink-0 text-primary" />
                <span>
                  For passwordless access, register a key in
                  <a href="/settings/ssh-keys" class="font-medium text-primary hover:underline">Settings → SSH Keys</a>.
                </span>
              </div>
            </Card>

            <!-- Billing -->
            <Card class="overflow-hidden">
              <div class="flex items-center gap-2.5 px-5 pb-4 pt-5">
                <span class="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Coins class="size-4" />
                </span>
                <h3 class="text-sm font-semibold">Billing</h3>
              </div>
              <dl class="divide-y divide-border/60 border-t border-border/60">
                {#each [
                  ['Rate', `${planRate} cr / hr`],
                  ['This session', `${sessionCost.toFixed(2)} cr`],
                  ['Total uptime', isRunning ? uptimeLabel : '—'],
                  ['Est. daily', `${(planRate * 24).toFixed(0)} cr`]
                ] as [label, value]}
                  <div class="flex items-center justify-between px-5 py-3">
                    <dt class="text-sm text-muted-foreground">{label}</dt>
                    <dd class="font-mono text-sm font-medium tabular-nums">{value}</dd>
                  </div>
                {/each}
              </dl>
              <div class="flex items-center gap-2 border-t border-border/60 bg-muted/30 px-5 py-3 text-xs text-muted-foreground">
                <Info class="size-3.5 shrink-0" />
                Billed per minute while the VM is running.
              </div>
            </Card>
          </div>
        </div>

        <!-- Usage trend — full width below the fold -->
        <div class="mt-4">
          <PodUsage podId={data.pod.id} />
        </div>
        </div>
      {/if}
    </div>
  </div>

  <Dialog
    bind:open={issueOpen}
    title="Report an issue with this VM"
    description="Describe what's wrong — SSH dropped, billing looks off, pod restarted, anything. Session ID and timestamp are attached automatically so an admin can trace it."
  >
    <div class="space-y-3">
      <div class="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs">
        <div class="font-mono text-muted-foreground">
          Session: <span class="text-foreground">{data.pod.id}</span>
        </div>
        <div class="font-mono text-muted-foreground">
          Timestamp: <span class="text-foreground">{new Date().toISOString()}</span>
        </div>
      </div>
      <Textarea
        bind:value={issueText}
        placeholder="What happened? Steps to reproduce, error messages, what you expected..."
        rows={6}
        maxlength={2000}
      />
      <p class="text-right text-xs text-muted-foreground">
        {issueText.length}/2000
      </p>
    </div>
    {#snippet footer()}
      <Button variant="outline" onclick={() => (issueOpen = false)}>Cancel</Button>
      <Button onclick={submitIssue} disabled={issueSubmitting || issueText.trim().length < 5}>
        {#if issueSubmitting}
          <Spinner class="size-4" /> Sending…
        {:else}
          Send report
        {/if}
      </Button>
    {/snippet}
  </Dialog>
{:else}
  <div class="flex flex-col items-center justify-center gap-3 py-24 text-center">
    <p class="text-sm text-muted-foreground">VM not found.</p>
    <Button href="/pods" variant="outline">
      <ArrowLeft class="size-4" /> Back to VMs
    </Button>
  </div>
{/if}
