<script lang="ts">
  import {
    Bot,
    Send,
    Sparkles,
    Wrench,
    Code2,
    Activity,
    Cpu,
    MemoryStick,
    HardDrive,
    AlertTriangle,
    RefreshCw,
    Server,
    User as UserIcon,
    Info
  } from 'lucide-svelte';
  import { Rocket } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import type { User } from '$lib/types';
  import { api, ApiError } from '$lib/api/client';
  import Markdown from '$lib/components/Markdown.svelte';
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
  import { cn } from '$lib/utils';

  let { data }: { data: { user: User | null } } = $props();

  const isAdmin = $derived(
    data.user?.role === 'admin' || data.user?.role === 'professor'
  );

  // ---- Free agents -------------------------------------------------------
  type AgentInfo = {
    agents: string[];
    provider: string;
    model: string;
    provider_available: boolean;
  };
  type ChatResponse = {
    agent: string;
    provider: string;
    model: string;
    reply: string;
  };

  const AGENT_META: Record<string, { label: string; blurb: string; icon: any }> = {
    hermes: { label: 'Hermes', blurb: 'General reasoning assistant', icon: Sparkles },
    clawbot: { label: 'Clawbot', blurb: 'Robotics & systems reasoning', icon: Wrench },
    opencode: { label: 'OpenCode', blurb: 'Coding assistant', icon: Code2 }
  };

  let info = $state<AgentInfo | null>(null);
  let selected = $state<string>('hermes');
  let prompt = $state('');
  let sending = $state(false);
  let launching = $state(false);
  type Turn = { role: 'user' | 'agent'; text: string; agent?: string };
  let transcript = $state<Turn[]>([]);

  const providerIsStub = $derived(info?.provider === 'stub');

  onMount(async () => {
    try {
      info = await api.get<AgentInfo>('/agents/');
      if (info.agents.length && !info.agents.includes(selected)) {
        selected = info.agents[0];
      }
    } catch {
      /* non-fatal — the chat still works, provider shows as unknown */
    }
  });

  async function send() {
    const text = prompt.trim();
    if (!text || sending) return;
    sending = true;
    transcript = [...transcript, { role: 'user', text }];
    prompt = '';
    try {
      const res = await api.post<ChatResponse>(`/agents/${selected}/chat`, {
        prompt: text
      });
      transcript = [...transcript, { role: 'agent', text: res.reply, agent: res.agent }];
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Agent request failed';
      toast.error('Agent error', { description: msg });
      transcript = [...transcript, { role: 'agent', text: `⚠️ ${msg}`, agent: selected }];
    } finally {
      sending = false;
    }
  }

  async function launchInVm() {
    if (launching) return;
    launching = true;
    const label = AGENT_META[selected]?.label ?? selected;
    const id = toast.loading(`Launching ${label} in a VM…`);
    try {
      const res = await api.post<{ agent: string; pod_id: string; state: string }>(
        `/agents/${selected}/launch`,
        { plan: 'small', template: 'ubuntu' }
      );
      toast.success(`${label} VM is ${res.state}`, {
        id,
        description: 'Opening the VM — run “hopper-agent” in its terminal.'
      });
      await goto(`/pods/${res.pod_id}`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Launch failed';
      toast.error('Could not launch VM', { id, description: msg });
    } finally {
      launching = false;
    }
  }

  // ---- Telemetry (admin) -------------------------------------------------
  type Snapshot = {
    cpu_percent: number;
    mem_percent: number;
    disk_percent: number;
    pods_by_state: Record<string, number>;
    recent_failures: number;
    error_rate: number;
  };
  type TelemetryResult = {
    ts?: string;
    severity?: string;
    findings?: string[];
    snapshot?: Snapshot;
    report?: string;
    status?: string;
  };

  let telemetry = $state<TelemetryResult | null>(null);
  let runningTelemetry = $state(false);

  const sevVariant = (s?: string): 'default' | 'secondary' =>
    s === 'critical' || s === 'warning' ? 'default' : 'secondary';
  const sevClass = (s?: string) =>
    s === 'critical'
      ? 'bg-rose-500/15 text-rose-600 dark:text-rose-400'
      : s === 'warning'
        ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400'
        : 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400';

  async function loadTelemetry() {
    try {
      telemetry = await api.get<TelemetryResult>('/agents/telemetry/latest');
    } catch {
      /* ignore — panel shows empty state */
    }
  }

  async function runTelemetry(notify = false) {
    if (runningTelemetry) return;
    runningTelemetry = true;
    const id = toast.loading(notify ? 'Running check & notifying you…' : 'Running telemetry check…');
    try {
      type TR = TelemetryResult & {
        notified?: Record<string, boolean> | { status: string };
      };
      const res = await api.post<TR>(`/agents/telemetry/run${notify ? '?notify=true' : ''}`);
      telemetry = res;
      if (notify) {
        const n = res.notified as any;
        if (!n || n.status === 'no_channels') {
          toast.error('No channel to notify', {
            id,
            description: 'Enable & save email or Telegram in Notifications first.'
          });
        } else {
          const ok = Object.entries(n)
            .filter(([, v]) => v === true)
            .map(([k]) => k);
          ok.length
            ? toast.success(`Report sent via ${ok.join(' + ')}`, { id })
            : toast.error('Report not delivered', {
                id,
                description: 'Check the channel config on the server.'
              });
        }
      } else {
        toast.success(`Telemetry: ${res.severity ?? 'done'}`, { id });
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Telemetry run failed';
      toast.error('Telemetry error', { id, description: msg });
    } finally {
      runningTelemetry = false;
    }
  }

  onMount(() => {
    if (isAdmin) loadTelemetry();
  });
</script>

<div class="space-y-6">
  <PageTitle
    title="AI Agents"
    description="Chat with free open-source agents, and monitor the always-on telemetry agent."
  />

  <!-- Free agents chat -->
  <Card class="animate-fade-up surface-glow overflow-hidden">
    <CardHeader>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle class="flex items-center gap-2">
            <span
              class="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-info text-primary-foreground shadow-sm"
            >
              <Bot class="size-4" />
            </span>
            Open-source agents
          </CardTitle>
          <CardDescription>
            Hermes, Clawbot and OpenCode — running on free backends (Groq /
            HuggingFace / local Ollama). No paid APIs.
          </CardDescription>
        </div>
        {#if info}
          <Badge variant={providerIsStub ? 'secondary' : 'default'}>
            <Server class="mr-1 size-3" />
            {info.provider}{info.model && info.provider !== 'stub' ? ` · ${info.model}` : ''}
          </Badge>
        {/if}
      </div>
    </CardHeader>
    <Separator />
    <CardContent class="space-y-4 pt-6">
      {#if providerIsStub}
        <div
          class="flex items-start gap-2 rounded-lg border border-info/30 bg-info/5 p-3 text-sm text-muted-foreground"
        >
          <Info class="mt-0.5 size-4 shrink-0 text-info" />
          <span>
            No free LLM backend is configured, so replies are placeholder echoes.
            Set <code class="font-mono text-xs">GROQ_API_KEY</code> or
            <code class="font-mono text-xs">HF_TOKEN</code> in the api-gateway
            <code class="font-mono text-xs">.env</code>, or run
            <code class="font-mono text-xs">ollama serve</code>, to get real answers.
          </span>
        </div>
      {/if}

      <!-- Agent picker -->
      <div class="grid gap-3 sm:grid-cols-3">
        {#each Object.entries(AGENT_META) as [key, meta] (key)}
          {@const disabled = info != null && !info.agents.includes(key)}
          <button
            type="button"
            {disabled}
            class={cn(
              'group flex items-center gap-2.5 rounded-xl border p-3 text-left transition-all',
              'hover:border-primary/50 hover:shadow-sm disabled:opacity-40',
              selected === key
                ? 'border-primary bg-primary/[0.04] ring-2 ring-primary/25'
                : 'border-border bg-card'
            )}
            onclick={() => (selected = key)}
          >
            <span
              class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground"
            >
              <meta.icon class="size-4" />
            </span>
            <span class="min-w-0">
              <span class="block text-sm font-semibold">{meta.label}</span>
              <span class="block truncate text-xs text-muted-foreground">{meta.blurb}</span>
            </span>
          </button>
        {/each}
      </div>

      <!-- Transcript -->
      {#if transcript.length}
        <div class="max-h-96 space-y-3 overflow-y-auto rounded-lg border border-border bg-muted/20 p-3">
          {#each transcript as turn, i (i)}
            <div class={cn('flex gap-2.5', turn.role === 'user' ? 'flex-row-reverse' : '')}>
              <span
                class={cn(
                  'flex size-7 shrink-0 items-center justify-center rounded-full',
                  turn.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground'
                )}
              >
                {#if turn.role === 'user'}<UserIcon class="size-3.5" />{:else}<Bot
                    class="size-3.5"
                  />{/if}
              </span>
              <div
                class={cn(
                  'max-w-[80%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm',
                  turn.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'border border-border bg-card'
                )}
              >
                {#if turn.role === 'agent' && turn.agent}
                  <div class="mb-0.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {AGENT_META[turn.agent]?.label ?? turn.agent}
                  </div>
                {/if}
                {#if turn.role === 'agent'}
                  <Markdown text={turn.text} />
                {:else}
                  {turn.text}
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {/if}

      <!-- Composer -->
      <div class="flex items-end gap-2">
        <Textarea
          bind:value={prompt}
          rows={2}
          maxlength={8000}
          placeholder={`Ask ${AGENT_META[selected]?.label ?? selected}…  (⌘/Ctrl+Enter to send)`}
          disabled={sending}
          onkeydown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') send();
          }}
        />
        <Button onclick={send} disabled={sending || !prompt.trim()}>
          <Send class="size-4" />
          {sending ? 'Sending…' : 'Send'}
        </Button>
      </div>

      <!-- Launch in a VM -->
      <div class="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-muted/20 p-3">
        <div class="min-w-0 flex-1">
          <div class="text-sm font-semibold">Run it in a VM</div>
          <div class="text-xs text-muted-foreground">
            Launch {AGENT_META[selected]?.label ?? selected} inside a fresh VM where it can
            read/write files and run commands. Open a terminal and run
            <code class="font-mono">hopper-agent</code>.
          </div>
        </div>
        <Button variant="secondary" onclick={launchInVm} disabled={launching || sending}>
          <Rocket class="size-4" />
          {launching ? 'Launching…' : `Launch ${AGENT_META[selected]?.label ?? selected} in VM`}
        </Button>
      </div>
    </CardContent>
  </Card>

  <!-- Telemetry monitor (admin/professor only) -->
  {#if isAdmin}
    <Card class="animate-fade-up overflow-hidden">
      <CardHeader>
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle class="flex items-center gap-2">
              <Activity class="size-5 text-primary" />
              Telemetry agent
            </CardTitle>
            <CardDescription>
              Always-on monitor: host CPU/memory/disk + VM health, with email /
              Telegram alerts on threshold breaches.
            </CardDescription>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onclick={() => runTelemetry(false)}
              disabled={runningTelemetry}
            >
              <RefreshCw class={cn('size-4', runningTelemetry && 'animate-spin')} />
              {runningTelemetry ? 'Running…' : 'Run check now'}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onclick={() => runTelemetry(true)}
              disabled={runningTelemetry}
            >
              <Send class="size-4" />
              Notify me
            </Button>
          </div>
        </div>
      </CardHeader>
      <Separator />
      <CardContent class="space-y-4 pt-6">
        {#if !telemetry || (telemetry.status && !telemetry.snapshot)}
          <p class="text-sm text-muted-foreground">
            {telemetry?.status ?? 'No telemetry run yet.'} Click “Run check now”.
          </p>
        {:else}
          <div class="flex flex-wrap items-center gap-3">
            <Badge variant={sevVariant(telemetry.severity)} class={sevClass(telemetry.severity)}>
              {(telemetry.severity ?? 'info').toUpperCase()}
            </Badge>
            {#if telemetry.ts}
              <span class="text-xs text-muted-foreground">
                {new Date(telemetry.ts).toLocaleString()}
              </span>
            {/if}
          </div>

          {#if telemetry.snapshot}
            {@const s = telemetry.snapshot}
            <div class="grid gap-3 sm:grid-cols-3">
              <div class="rounded-lg border border-border p-3">
                <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Cpu class="size-3.5" /> CPU
                </div>
                <div class="mt-1 text-lg font-semibold">{s.cpu_percent.toFixed(0)}%</div>
              </div>
              <div class="rounded-lg border border-border p-3">
                <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <MemoryStick class="size-3.5" /> Memory
                </div>
                <div class="mt-1 text-lg font-semibold">{s.mem_percent.toFixed(0)}%</div>
              </div>
              <div
                class={cn(
                  'rounded-lg border p-3',
                  s.disk_percent >= 90 ? 'border-amber-500/40 bg-amber-500/[0.04]' : 'border-border'
                )}
              >
                <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <HardDrive class="size-3.5" /> Disk
                </div>
                <div class="mt-1 text-lg font-semibold">{s.disk_percent.toFixed(0)}%</div>
              </div>
            </div>
            <div class="flex flex-wrap gap-2 text-xs">
              {#each Object.entries(s.pods_by_state) as [state, n] (state)}
                <Badge variant="secondary">{state}: {n}</Badge>
              {/each}
              <Badge variant="secondary">failures/1h: {s.recent_failures}</Badge>
              <Badge variant="secondary">error-rate: {(s.error_rate * 100).toFixed(0)}%</Badge>
            </div>
          {/if}

          {#if telemetry.findings?.length}
            <div>
              <h4 class="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Findings
              </h4>
              <ul class="space-y-1 text-sm">
                {#each telemetry.findings as f (f)}
                  <li class="flex items-start gap-2">
                    <AlertTriangle
                      class={cn(
                        'mt-0.5 size-3.5 shrink-0',
                        telemetry.severity === 'info' ? 'text-muted-foreground' : 'text-amber-500'
                      )}
                    />
                    <span>{f}</span>
                  </li>
                {/each}
              </ul>
            </div>
          {/if}
        {/if}
      </CardContent>
    </Card>
  {/if}
</div>
