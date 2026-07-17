<script lang="ts">
  import {
    Square,
    ArrowLeft,
    Terminal as TerminalIcon,
    Activity,
    LineChart,
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
    Cpu,
    MemoryStick,
    Server,
    Clock,
    KeyRound,
    Layers,
    Box,
    Boxes,
    HardDrive
  } from 'lucide-svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { invalidateAll, goto } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import GpuMetrics from '$lib/components/GpuMetrics.svelte';
  import Terminal from '$lib/components/Terminal.svelte';
  import PodUsage from '$lib/components/PodUsage.svelte';
  import PodFiles from '$lib/components/PodFiles.svelte';
  import PageTitle from '$lib/components/PageTitle.svelte';
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
  import type { Pod, User, VmMetrics } from '$lib/types';

  let {
    data
  }: {
    data: { pod: Pod | null; nodeIp: string; user: User | null };
  } = $props();

  let metrics = $state<VmMetrics | null>(null);

  let activeTab = $state('terminal');
  let showPassword = $state(false);

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

  function vscodeUrl(p: Pod): string {
    return `/${data.user?.id ?? ''}/code/${p.id}/`;
  }
  function getPreviewUrl(p: Pod, port: number): string {
    return `/${data.user?.id ?? ''}/code/${p.id}/proxy/${port}/`;
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
    class={cn(
      'flex flex-col',
      activeTab === 'terminal' && 'h-[calc(100vh-7rem)]'
    )}
  >
    <!-- Header -->
    <div class="mb-5 shrink-0">
      <a
        href="/pods"
        class="group mb-2 inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft class="size-4 transition-transform group-hover:-translate-x-0.5" />
        Back to VMs
      </a>
      <PageTitle
        mono
        title={shortId(data.pod.id, 12)}
        description={`${data.pod.plan} · ${data.pod.image} · created ${relTime(data.pod.created_at)}`}
      >
        {#snippet badge()}
          <Badge variant={cfg.variant}>
            {#if cfg.pulse}
              <Spinner class="size-3" />
            {/if}
            {cfg.label}
          </Badge>
        {/snippet}
        {#snippet action()}
          <div class="flex flex-wrap items-center gap-2">
            {#if isRunning && pod.vscode_port}
              <Button
                variant="outline"
                href={vscodeUrl(pod)}
                target="_blank"
                rel="noopener noreferrer"
              >
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
        {/snippet}
      </PageTitle>
    </div>

    <!-- Tabs -->
    <Tabs.Root bind:value={activeTab} class="flex min-h-0 flex-1 flex-col">
      <Tabs.List class="mb-4 mt-1 self-start">
        <Tabs.Trigger value="terminal">
          <TerminalIcon class="size-3.5" /> Terminal
        </Tabs.Trigger>
        <Tabs.Trigger value="metrics">
          <Activity class="size-3.5" /> Metrics
        </Tabs.Trigger>
        <Tabs.Trigger value="usage">
          <LineChart class="size-3.5" /> Usage
        </Tabs.Trigger>
        <Tabs.Trigger value="files">
          <FileUp class="size-3.5" /> Files
        </Tabs.Trigger>
        <Tabs.Trigger value="details">
          <Info class="size-3.5" /> Details
        </Tabs.Trigger>
      </Tabs.List>

      <!-- Terminal -->
      <Tabs.Content value="terminal" class="min-h-0 flex-1">
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
      </Tabs.Content>

      <!-- Metrics -->
      <Tabs.Content value="metrics" class="min-h-0 flex-1 overflow-y-auto">
        {#if isRunning}
          <div class="space-y-4">
            <GpuMetrics {metrics} />

            <!-- Allocation snapshot — modern, minimal segmented strip. -->
            <Card
              class="grid grid-cols-2 gap-px overflow-hidden bg-border/60 lg:grid-cols-4"
            >
              <div class="flex items-center gap-3 bg-card p-4">
                <span class="flex size-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <Server class="size-4" />
                </span>
                <div class="min-w-0">
                  <div class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Plan
                  </div>
                  <div class="truncate text-base font-semibold capitalize">{data.pod.plan}</div>
                </div>
              </div>
              <div class="flex items-center gap-3 bg-card p-4">
                <span class="flex size-9 items-center justify-center rounded-xl bg-info/10 text-info">
                  <Cpu class="size-4" />
                </span>
                <div class="min-w-0">
                  <div class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    vCPU
                  </div>
                  <div class="truncate text-base font-semibold">{data.pod.cpu ?? '—'}</div>
                </div>
              </div>
              <div class="flex items-center gap-3 bg-card p-4">
                <span class="flex size-9 items-center justify-center rounded-xl bg-success/10 text-success">
                  <MemoryStick class="size-4" />
                </span>
                <div class="min-w-0">
                  <div class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Memory
                  </div>
                  <div class="truncate text-base font-semibold">{data.pod.memory ?? '—'}</div>
                </div>
              </div>
              <div class="flex items-center gap-3 bg-card p-4">
                <span class="flex size-9 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                  <Clock class="size-4" />
                </span>
                <div class="min-w-0">
                  <div class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Uptime
                  </div>
                  <div class="truncate text-base font-semibold">{relTime(data.pod.created_at)}</div>
                </div>
              </div>
            </Card>
          </div>
        {:else}
          <Card class="border-dashed">
            <CardContent class="py-12 text-center text-sm text-muted-foreground">
              Live metrics are only available when the VM is running.
            </CardContent>
          </Card>
        {/if}
      </Tabs.Content>

      <!-- Usage -->
      <Tabs.Content value="usage" class="min-h-0 flex-1 overflow-y-auto">
        <PodUsage podId={data.pod.id} />
      </Tabs.Content>

      <!-- Files -->
      <Tabs.Content value="files" class="min-h-0 flex-1 overflow-y-auto">
        <PodFiles podId={data.pod.id} podRunning={isRunning} />
      </Tabs.Content>

      <!-- Details -->
      <Tabs.Content value="details" class="min-h-0 flex-1 overflow-y-auto">
        <div class="grid gap-4 lg:grid-cols-2">
          <!-- Specifications — edge-to-edge hairline grid -->
          <Card class="overflow-hidden">
            <div class="flex items-center gap-2.5 px-5 pb-4 pt-5">
              <span
                class="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary"
              >
                <Server class="size-4" />
              </span>
              <h3 class="text-sm font-semibold">Specifications</h3>
            </div>
            <dl class="grid grid-cols-2 gap-px border-t border-border/60 bg-border/60">
              <div class="bg-card px-5 py-3.5">
                <dt class="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  <Layers class="size-3" /> Plan
                </dt>
                <dd class="mt-1 text-sm font-medium capitalize">{data.pod.plan}</dd>
              </div>
              <div class="bg-card px-5 py-3.5">
                <dt class="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  <Cpu class="size-3" /> Resources
                </dt>
                <dd class="mt-1 text-sm font-medium">
                  {data.pod.cpu ?? '—'} vCPU · {data.pod.memory ?? '—'}
                </dd>
              </div>
              <div class="col-span-2 bg-card px-5 py-3.5">
                <dt class="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  <Box class="size-3" /> Image
                </dt>
                <dd class="mt-1 truncate font-mono text-xs">{data.pod.image}</dd>
              </div>
              <div class="bg-card px-5 py-3.5">
                <dt class="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  <Boxes class="size-3" /> Namespace
                </dt>
                <dd class="mt-1 font-mono text-xs">{data.pod.namespace}</dd>
              </div>
              <div class="bg-card px-5 py-3.5">
                <dt class="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  <HardDrive class="size-3" /> Node
                </dt>
                <dd class="mt-1 font-mono text-xs">{data.pod.node_name ?? '—'}</dd>
              </div>
              <div class="col-span-2 bg-card px-5 py-3.5">
                <dt class="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  <Clock class="size-3" /> Created
                </dt>
                <dd class="mt-1 text-sm">{new Date(data.pod.created_at).toLocaleString()}</dd>
              </div>
            </dl>
          </Card>

          <!-- Access — modern fields with inline actions -->
          <Card class="overflow-hidden">
            <div class="flex items-center gap-2.5 px-5 pb-4 pt-5">
              <span
                class="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary"
              >
                <KeyRound class="size-4" />
              </span>
              <h3 class="text-sm font-semibold">Access</h3>
            </div>
            <div class="space-y-4 border-t border-border/60 px-5 py-5">
              {#if data.pod.state === 'running' && data.pod.ssh_port}
                <div class="space-y-1.5">
                  <div class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    SSH command
                  </div>
                  <div class="relative">
                    <code
                      class="block w-full select-all overflow-x-auto whitespace-nowrap rounded-lg border border-border/60 bg-muted/50 py-2.5 pl-3 pr-11 font-mono text-xs"
                    >
                      ssh root@{data.nodeIp} -p {data.pod.ssh_port}
                    </code>
                    <button
                      class="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
                      title="Copy command"
                      aria-label="Copy SSH command"
                      onclick={() =>
                        copyText(
                          `ssh root@${data.nodeIp} -p ${data.pod!.ssh_port}`,
                          'SSH command copied'
                        )}
                    >
                      <Copy class="size-3.5" />
                    </button>
                  </div>
                </div>
              {/if}

              {#if data.pod.ssh_password}
                <div class="space-y-1.5">
                  <div class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Root password
                  </div>
                  <div class="relative">
                    <code
                      class="block w-full select-all overflow-x-auto whitespace-nowrap rounded-lg border border-border/60 bg-muted/50 py-2.5 pl-3 pr-[4.75rem] font-mono text-xs {showPassword
                        ? ''
                        : 'tracking-widest'}"
                    >
                      {showPassword
                        ? data.pod.ssh_password
                        : '•'.repeat(Math.min(20, data.pod.ssh_password.length))}
                    </code>
                    <div class="absolute right-1.5 top-1/2 flex -translate-y-1/2 items-center gap-0.5">
                      <button
                        class="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
                        title={showPassword ? 'Hide' : 'Reveal'}
                        aria-label={showPassword ? 'Hide password' : 'Reveal password'}
                        onclick={() => (showPassword = !showPassword)}
                      >
                        {#if showPassword}
                          <EyeOff class="size-3.5" />
                        {:else}
                          <Eye class="size-3.5" />
                        {/if}
                      </button>
                      <button
                        class="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
                        title="Copy password"
                        aria-label="Copy password"
                        onclick={() =>
                          copyText(data.pod!.ssh_password ?? '', 'Password copied')}
                      >
                        <Copy class="size-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              {/if}

              {#if isRunning && data.pod.vscode_port}
                <div class="space-y-1.5">
                  <div class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Web tools
                  </div>
                  <div class="flex flex-wrap gap-2">
                    <Button
                      href={vscodeUrl(data.pod)}
                      target="_blank"
                      rel="noopener noreferrer"
                      class="flex-1"
                    >
                      <Code2 class="size-4" /> Open VS Code
                      <ExternalLink class="ml-auto size-3 opacity-60" />
                    </Button>
                    <Button
                      href={getPreviewUrl(data.pod, 5000)}
                      variant="outline"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Preview :5000 <ExternalLink class="size-3 opacity-60" />
                    </Button>
                  </div>
                </div>
              {/if}

              <div
                class="flex items-start gap-2 rounded-lg border border-border/60 bg-muted/30 px-3 py-2.5 text-xs text-muted-foreground"
              >
                <KeyRound class="mt-0.5 size-3.5 shrink-0 text-primary" />
                <span>
                  For passwordless access, register a key in
                  <a href="/settings/ssh-keys" class="font-medium text-primary hover:underline">
                    Settings → SSH Keys
                  </a>.
                </span>
              </div>
            </div>
          </Card>
        </div>
      </Tabs.Content>
    </Tabs.Root>
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
