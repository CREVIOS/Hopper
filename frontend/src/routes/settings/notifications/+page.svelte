<script lang="ts">
  import { Bell, Send, Save, Info, AlertTriangle } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import { toast } from 'svelte-sonner';
  import { api, ApiError } from '$lib/api/client';
  import {
    Button,
    Card,
    CardHeader,
    CardTitle,
    CardDescription,
    CardContent,
    Input,
    Label,
    Switch,
    Separator,
    Badge
  } from '$lib/ui';
  import PageTitle from '$lib/components/PageTitle.svelte';
  import { cn } from '$lib/utils';

  type Pref = {
    telegram_enabled: boolean;
    telegram_number: string;
    min_severity: string;
    telegram_configured: boolean;
  };

  let telegramEnabled = $state(false);
  let telegramNumber = $state('');
  let minSeverity = $state<'info' | 'warning' | 'critical'>('warning');
  let telegramConfigured = $state(false);

  let loading = $state(true);
  let saving = $state(false);
  let testing = $state(false);

  const SEVERITIES: { key: 'info' | 'warning' | 'critical'; label: string; hint: string }[] = [
    { key: 'info', label: 'All', hint: 'Every report, including healthy' },
    { key: 'warning', label: 'Warning+', hint: 'Warnings and criticals' },
    { key: 'critical', label: 'Critical only', hint: 'Only urgent issues' }
  ];

  onMount(async () => {
    try {
      const p = await api.get<Pref>('/settings/alerts');
      telegramEnabled = p.telegram_enabled;
      telegramNumber = p.telegram_number;
      minSeverity = (p.min_severity as any) || 'warning';
      telegramConfigured = p.telegram_configured;
    } catch {
      toast.error('Could not load your notification settings');
    } finally {
      loading = false;
    }
  });

  async function save() {
    if (saving) return;
    saving = true;
    const id = toast.loading('Saving…');
    try {
      // Email is disabled as a channel — always send it off.
      await api.put<Pref>('/settings/alerts', {
        email_enabled: false,
        email_address: '',
        telegram_enabled: telegramEnabled,
        telegram_number: telegramNumber.trim(),
        min_severity: minSeverity
      });
      toast.success('Notification settings saved', { id });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Save failed';
      toast.error('Could not save', { id, description: msg });
    } finally {
      saving = false;
    }
  }

  async function sendTest() {
    if (testing) return;
    testing = true;
    const id = toast.loading('Sending test alert…');
    try {
      const res = await api.post<{
        status: string;
        delivered?: Record<string, boolean>;
        reasons?: Record<string, string>;
      }>('/settings/alerts/test');
      if (res.status === 'no_channels') {
        toast.error('No channel enabled', {
          id,
          description: 'Enable and save Telegram first.'
        });
      } else {
        const entries = Object.entries(res.delivered ?? {});
        const ok = entries.filter(([, v]) => v).map(([k]) => k);
        const failed = entries.filter(([, v]) => !v).map(([k]) => k);
        // Surface a specific server reason (e.g. Telegram gateway unauthorized).
        const reason = res.reasons ? Object.values(res.reasons)[0] : undefined;
        if (ok.length) {
          toast.success(`Test sent via ${ok.join(' + ')}`, {
            id,
            description:
              failed.length && reason ? `${failed.join(', ')} failed: ${reason}` : 'Check your Telegram.'
          });
        } else {
          toast.error('Test could not be delivered', {
            id,
            description: reason ?? 'Check the credentials/provider config on the server.'
          });
        }
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Test failed';
      toast.error('Test failed', { id, description: msg });
    } finally {
      testing = false;
    }
  }
</script>

<div class="space-y-6">
  <PageTitle
    title="Notifications"
    description="Choose how the always-on telemetry agent alerts you when something needs attention."
  />

  <Card class="animate-fade-up surface-glow overflow-hidden">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <span
          class="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-info text-primary-foreground shadow-sm"
        >
          <Bell class="size-4" />
        </span>
        Alert channels
      </CardTitle>
      <CardDescription>
        These are your personal destinations — each subscribed user gets their own
        alerts. Sending accounts are managed by the platform.
      </CardDescription>
    </CardHeader>
    <Separator />
    <CardContent class="space-y-6 pt-6">
      {#if loading}
        <p class="text-sm text-muted-foreground">Loading…</p>
      {:else}
        <!-- Telegram -->
        <div class="space-y-3">
          <div class="flex items-center justify-between gap-4">
            <div class="flex items-center gap-2.5">
              <Send class="size-4 text-muted-foreground" />
              <div>
                <div class="flex items-center gap-2 text-sm font-semibold">
                  Telegram
                  {#if telegramConfigured}
                    <Badge variant="secondary" class="text-[10px]">Green API</Badge>
                  {/if}
                </div>
                <div class="text-xs text-muted-foreground">Receive alerts on Telegram</div>
              </div>
            </div>
            <Switch bind:checked={telegramEnabled} disabled={!telegramConfigured} />
          </div>
          {#if !telegramConfigured}
            <div
              class="flex items-start gap-2 rounded-lg border border-info/30 bg-info/5 p-3 text-xs text-muted-foreground"
            >
              <Info class="mt-0.5 size-3.5 shrink-0 text-info" />
              Telegram delivery isn't configured on the server yet
              (<code class="font-mono">GREEN_API_ID_INSTANCE</code> /
              <code class="font-mono">GREEN_API_TOKEN</code>). You can still save a number;
              it'll activate once an admin enables the gateway.
            </div>
          {/if}
          {#if telegramEnabled || telegramNumber}
            <div class="pl-6">
              <Label for="tg" class="text-xs text-muted-foreground">
                Your Telegram phone number (international format)
              </Label>
              <Input
                id="tg"
                bind:value={telegramNumber}
                placeholder="+8801712345678"
                class="mt-1 max-w-sm"
              />
              <p class="mt-1.5 text-[11px] text-muted-foreground">
                Use the phone number on your Telegram account. Start a chat with the Hopper
                bot first so it can message you.
              </p>
            </div>
          {/if}
        </div>

        <Separator />

        <!-- Severity -->
        <div class="space-y-2">
          <div class="flex items-center gap-2.5">
            <AlertTriangle class="size-4 text-muted-foreground" />
            <div class="text-sm font-semibold">Alert me for</div>
          </div>
          <div class="grid gap-2 sm:grid-cols-3">
            {#each SEVERITIES as s (s.key)}
              <button
                type="button"
                class={cn(
                  'rounded-xl border p-3 text-left transition-all hover:border-primary/50',
                  minSeverity === s.key
                    ? 'border-primary bg-primary/[0.04] ring-2 ring-primary/25'
                    : 'border-border bg-card'
                )}
                onclick={() => (minSeverity = s.key)}
              >
                <div class="text-sm font-semibold">{s.label}</div>
                <div class="mt-0.5 text-xs text-muted-foreground">{s.hint}</div>
              </button>
            {/each}
          </div>
        </div>

        <!-- Actions -->
        <div class="flex flex-wrap items-center gap-3 pt-1">
          <Button onclick={save} disabled={saving}>
            <Save class="size-4" />
            {saving ? 'Saving…' : 'Save preferences'}
          </Button>
          <Button variant="outline" onclick={sendTest} disabled={testing || !telegramEnabled}>
            <Send class="size-4" />
            {testing ? 'Sending…' : 'Send test alert'}
          </Button>
          <span class="text-xs text-muted-foreground">Save first, then send a test.</span>
        </div>
      {/if}
    </CardContent>
  </Card>
</div>
