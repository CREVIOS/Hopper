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
    Loader2,
    Code2,
    MessageSquareWarning
  } from 'lucide-svelte';
  import { invalidateAll, goto } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import GpuMetrics from '$lib/components/GpuMetrics.svelte';
  import Terminal from '$lib/components/Terminal.svelte';
  import PodUsage from '$lib/components/PodUsage.svelte';
  import PodFiles from '$lib/components/PodFiles.svelte';
  import { api, ApiError } from '$lib/api/client';
  import { confirm } from '$lib/confirm.svelte';
  import { copyToClipboard, relTime, shortId } from '$lib/utils';
  import {
    Button,
    Card,
    CardContent,
    Badge,
    Tabs,
    Separator,
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
  {@const podState = data.pod.state}
  {@const cfg = stateBadge[podState] ?? stateBadge.terminated}
  {@const isRunning = podState === 'running'}
  {@const canTerminate = !['terminated', 'failed'].includes(podState)}

  <div class="flex h-[calc(100vh-7rem)] flex-col">
    <!-- Header -->
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <Button href="/pods" variant="ghost" size="icon" aria-label="Back">
          <ArrowLeft class="size-4" />
        </Button>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="font-mono text-xl font-bold tracking-tight">
              {shortId(data.pod.id, 12)}
            </h1>
            <Badge variant={cfg.variant}>
              {#if cfg.pulse}
                <Loader2 class="size-3 animate-spin" />
              {/if}
              {cfg.label}
            </Badge>
          </div>
          <p class="mt-0.5 text-xs text-muted-foreground">
            {data.pod.plan} · {data.pod.image} · created {relTime(data.pod.created_at)}
          </p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        {#if isRunning && data.pod.vscode_port}
          <Button
            variant="outline"
            href={vscodeUrl(data.pod)}
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
    </div>

    <!-- Tabs -->
    <Tabs.Root bind:value={activeTab} class="flex min-h-0 flex-1 flex-col">
      <Tabs.List>
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
            <Tooltip content="New terminal">
              <button
                class="px-3 py-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                onclick={addTerminal}
                aria-label="New terminal"
              >
                <Plus class="size-4" />
              </button>
            </Tooltip>
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
          <GpuMetrics {metrics} />
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
          <Card>
            <CardContent class="space-y-4 pt-6">
              <h3 class="text-sm font-semibold">Specifications</h3>
              <Separator />
              <dl class="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                <dt class="text-muted-foreground">Plan</dt>
                <dd class="font-medium capitalize">{data.pod.plan}</dd>

                <dt class="text-muted-foreground">Image</dt>
                <dd class="font-mono text-xs">{data.pod.image}</dd>

                <dt class="text-muted-foreground">Resources</dt>
                <dd class="font-medium">
                  {data.pod.cpu ?? '—'} vCPU · {data.pod.memory ?? '—'}
                </dd>

                <dt class="text-muted-foreground">Namespace</dt>
                <dd class="font-mono text-xs">{data.pod.namespace}</dd>

                <dt class="text-muted-foreground">Node</dt>
                <dd class="font-mono text-xs">{data.pod.node_name ?? '—'}</dd>

                <dt class="text-muted-foreground">Created</dt>
                <dd>{new Date(data.pod.created_at).toLocaleString()}</dd>
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardContent class="space-y-4 pt-6">
              <h3 class="text-sm font-semibold">Access</h3>
              <Separator />
              {#if data.pod.state === 'running' && data.pod.ssh_port}
                <div class="space-y-1.5">
                  <div class="text-xs font-medium text-muted-foreground">
                    SSH command
                  </div>
                  <div class="flex items-center gap-2">
                    <code
                      class="flex-1 select-all rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs"
                    >
                      ssh root@{data.nodeIp} -p {data.pod.ssh_port}
                    </code>
                    <Tooltip content="Copy command">
                      <Button
                        variant="outline"
                        size="icon"
                        onclick={() =>
                          copyText(
                            `ssh root@${data.nodeIp} -p ${data.pod!.ssh_port}`,
                            'SSH command copied'
                          )}
                      >
                        <Copy class="size-3.5" />
                      </Button>
                    </Tooltip>
                  </div>
                </div>
              {/if}

              {#if data.pod.ssh_password}
                <div class="space-y-1.5">
                  <div class="text-xs font-medium text-muted-foreground">
                    Root password
                  </div>
                  <div class="flex items-center gap-2">
                    <code
                      class="flex-1 select-all rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs tracking-widest"
                    >
                      {showPassword
                        ? data.pod.ssh_password
                        : '•'.repeat(Math.min(20, data.pod.ssh_password.length))}
                    </code>
                    <Tooltip content={showPassword ? 'Hide' : 'Reveal'}>
                      <Button
                        variant="outline"
                        size="icon"
                        onclick={() => (showPassword = !showPassword)}
                      >
                        {#if showPassword}
                          <EyeOff class="size-3.5" />
                        {:else}
                          <Eye class="size-3.5" />
                        {/if}
                      </Button>
                    </Tooltip>
                    <Tooltip content="Copy password">
                      <Button
                        variant="outline"
                        size="icon"
                        onclick={() =>
                          copyText(data.pod!.ssh_password ?? '', 'Password copied')}
                      >
                        <Copy class="size-3.5" />
                      </Button>
                    </Tooltip>
                  </div>
                </div>
              {/if}

              {#if isRunning && data.pod.vscode_port}
                <div class="space-y-1.5">
                  <div class="text-xs font-medium text-muted-foreground">
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

              <div class="rounded-lg bg-muted/40 p-3 text-xs text-muted-foreground">
                For passwordless access, register a key in
                <a href="/settings/ssh-keys" class="font-medium text-primary hover:underline">
                  Settings → SSH Keys
                </a>.
              </div>
            </CardContent>
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
          <Loader2 class="size-4 animate-spin" /> Sending…
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
