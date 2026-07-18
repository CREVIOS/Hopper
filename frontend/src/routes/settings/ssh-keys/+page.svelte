<script lang="ts">
  import {
    KeyRound,
    Plus,
    Trash2,
    Copy,
    Fingerprint,
    ShieldCheck,
    Terminal,
    Check
  } from 'lucide-svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { invalidateAll } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import {
    Button,
    Card,
    CardContent,
    Dialog,
    Input,
    Label,
    Textarea,
    Badge,
    Tooltip
  } from '$lib/ui';
  import { api, ApiError } from '$lib/api/client';
  import PageTitle from '$lib/components/PageTitle.svelte';
  import { confirm } from '$lib/confirm.svelte';
  import { copyToClipboard, relTime } from '$lib/utils';
  import type { SshKey } from '$lib/types';

  type ApiKey = {
    id: string;
    name: string;
    prefix: string;
    scope: string;
    created_at: string;
    last_used_at: string | null;
    revoked_at: string | null;
  };

  let { data }: { data: { keys: SshKey[]; apiKeys: ApiKey[] } } = $props();

  const activeApiKeys = $derived(data.apiKeys.filter((k) => !k.revoked_at));

  const MAX_KEYS = 10;
  const usedPct = $derived((data.keys.length / MAX_KEYS) * 100);
  const atLimit = $derived(data.keys.length >= MAX_KEYS);

  // Derive the key algorithm from the public key for a small, modest type chip.
  function keyAlgo(pk: string): { label: string; tint: string } {
    const prefix = pk?.trim().split(/\s+/)[0]?.toLowerCase() ?? '';
    if (prefix.includes('ed25519'))
      return { label: 'ED25519', tint: 'text-success bg-success/10 ring-success/20' };
    if (prefix.includes('rsa'))
      return { label: 'RSA', tint: 'text-info bg-info/10 ring-info/20' };
    if (prefix.includes('ecdsa'))
      return { label: 'ECDSA', tint: 'text-primary bg-primary/10 ring-primary/20' };
    if (prefix.includes('dss'))
      return { label: 'DSA', tint: 'text-warning bg-warning/10 ring-warning/20' };
    return { label: 'KEY', tint: 'text-muted-foreground bg-muted ring-border' };
  }

  const KEYGEN_SNIPPET = `# Generate a new ed25519 key (skip if you already have one)
ssh-keygen -t ed25519 -C "you@example.edu"

# Copy the PUBLIC key to clipboard
cat ~/.ssh/id_ed25519.pub | pbcopy   # macOS
cat ~/.ssh/id_ed25519.pub | xclip    # Linux`;

  async function copySnippet() {
    try {
      await copyToClipboard(KEYGEN_SNIPPET);
      toast.success('Commands copied');
    } catch {
      toast.error('Could not access clipboard');
    }
  }

  let dialogOpen = $state(false);
  let newName = $state('');
  let newKey = $state('');
  let saving = $state(false);

  function reset() {
    newName = '';
    newKey = '';
    saving = false;
  }

  function validKey(k: string): boolean {
    return /^(ssh-rsa|ssh-ed25519|ecdsa-sha2|ssh-dss)\s+/i.test(k.trim());
  }

  async function addKey() {
    if (saving) return;
    const name = newName.trim();
    const key = newKey.trim();
    if (!name) {
      toast.error('Give the key a name');
      return;
    }
    if (!validKey(key)) {
      toast.error(
        'Public key looks invalid. It should start with ssh-rsa, ssh-ed25519, ecdsa-sha2, or ssh-dss'
      );
      return;
    }
    saving = true;
    const id = toast.loading('Adding key…');
    try {
      await api.post('/ssh-keys/', { name, public_key: key });
      toast.success('SSH key added', { id });
      dialogOpen = false;
      reset();
      await invalidateAll();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Failed to add key';
      toast.error('Could not add key', { id, description: msg });
    } finally {
      saving = false;
    }
  }

  async function deleteKey(k: SshKey) {
    const ok = await confirm({
      title: `Remove key "${k.name}"?`,
      description:
        'Devices using this key will no longer be able to SSH into your VMs.',
      confirmLabel: 'Remove',
      variant: 'destructive'
    });
    if (!ok) return;
    const id = toast.loading('Removing key…');
    try {
      await api.delete(`/ssh-keys/${k.id}`);
      toast.success('SSH key removed', { id });
      await invalidateAll();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Failed to remove key';
      toast.error('Could not remove key', { id, description: msg });
    }
  }

  async function copyFingerprint(fp: string) {
    try {
      await copyToClipboard(fp);
      toast.success('Fingerprint copied');
    } catch {
      toast.error('Could not access clipboard');
    }
  }

  // --- API keys (programmatic access) ---
  let apiDialogOpen = $state(false);
  let apiKeyName = $state('');
  let apiKeyScope = $state<'read_only' | 'full_access'>('read_only');
  let apiKeySaving = $state(false);
  // The plaintext token — returned exactly once at creation, shown until dismissed.
  let createdToken = $state<string | null>(null);

  async function createApiKey() {
    if (apiKeySaving) return;
    const name = apiKeyName.trim();
    if (!name) {
      toast.error('Give the key a name');
      return;
    }
    apiKeySaving = true;
    const id = toast.loading('Creating API key…');
    try {
      const res = await api.post<{ key: string }>('/auth/api-keys', {
        name,
        scope: apiKeyScope
      });
      createdToken = res.key;
      toast.success('API key created', { id, description: 'Copy it now — it is shown only once.' });
      apiKeyName = '';
      apiKeyScope = 'read_only';
      await invalidateAll();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Failed to create API key';
      toast.error('Could not create API key', { id, description: msg });
    } finally {
      apiKeySaving = false;
    }
  }

  async function revokeApiKey(k: ApiKey) {
    const ok = await confirm({
      title: `Revoke "${k.name}"?`,
      description: 'Requests using this key will start failing immediately. This cannot be undone.',
      confirmLabel: 'Revoke',
      variant: 'destructive'
    });
    if (!ok) return;
    const id = toast.loading('Revoking key…');
    try {
      await api.delete(`/auth/api-keys/${k.id}`);
      toast.success('API key revoked', { id });
      await invalidateAll();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Failed to revoke key';
      toast.error('Could not revoke key', { id, description: msg });
    }
  }

  async function copyToken() {
    if (!createdToken) return;
    try {
      await copyToClipboard(createdToken);
      toast.success('Token copied');
    } catch {
      toast.error('Could not access clipboard');
    }
  }
</script>

<div class="space-y-6">
  <PageTitle
    title="SSH keys"
    eyebrow="Settings"
    eyebrowIcon={KeyRound}
    description="Public keys registered here are pushed to every VM you launch, enabling passwordless SSH from any device whose private key matches."
  >
    {#snippet action()}
      <Button onclick={() => (dialogOpen = true)} disabled={data.keys.length >= MAX_KEYS}>
        <Plus class="size-4" /> Add SSH key
      </Button>
    {/snippet}
  </PageTitle>

  <!-- Capacity panel — segmented slot meter for the per-account key limit. -->
  <Card class="animate-fade-up surface-glow overflow-hidden">
    <CardContent class="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-center gap-3.5">
        <div class="grid size-11 place-items-center rounded-xl bg-primary/10 text-primary ring-1 ring-inset ring-primary/20">
          <ShieldCheck class="size-5" strokeWidth={1.75} />
        </div>
        <div>
          <div class="flex items-baseline gap-1.5">
            <span class="font-mono text-2xl font-bold tracking-tight tabular-nums">{data.keys.length}</span>
            <span class="text-sm text-muted-foreground">of {MAX_KEYS} keys used</span>
          </div>
          <p class="mt-0.5 text-sm text-muted-foreground">
            {#if atLimit}
              You've reached the limit. Remove one to add another.
            {:else}
              {MAX_KEYS - data.keys.length} slot{MAX_KEYS - data.keys.length === 1 ? '' : 's'} remaining on your account.
            {/if}
          </p>
        </div>
      </div>
      <div class="w-full sm:w-72">
        <div class="flex items-center gap-1.5">
          {#each { length: MAX_KEYS } as _, i (i)}
            <span
              class={`h-2 flex-1 rounded-full transition-all duration-500 ${
                i < data.keys.length
                  ? atLimit
                    ? 'bg-destructive'
                    : 'bg-primary'
                  : 'bg-muted'
              }`}
              style="transition-delay: {i * 35}ms"
            ></span>
          {/each}
        </div>
        <div class="mt-2.5 flex items-center justify-between font-mono text-[11px] font-medium uppercase tracking-[0.12em]">
          <span class="text-muted-foreground tabular-nums">{data.keys.length} used · {MAX_KEYS - data.keys.length} free</span>
          <span class={`tabular-nums ${atLimit ? 'text-destructive' : 'text-muted-foreground'}`}>{Math.round(usedPct)}% full</span>
        </div>
      </div>
    </CardContent>
  </Card>

  {#if data.keys.length === 0}
    <Card class="animate-fade-up surface-glow overflow-hidden border-dashed" style="animation-delay: 60ms">
      <CardContent class="flex flex-col items-center gap-5 py-16 text-center">
        <div class="grid size-14 place-items-center rounded-2xl bg-primary/10 text-primary ring-1 ring-inset ring-primary/20">
          <KeyRound class="size-6" strokeWidth={1.75} />
        </div>
        <div>
          <p class="text-base font-semibold tracking-tight">No keys registered yet</p>
          <p class="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">
            Add your laptop's public key (usually <code
              class="rounded bg-muted px-1 py-0.5 font-mono text-xs">~/.ssh/id_ed25519.pub</code
            >) so you can SSH into VMs without typing the root password.
          </p>
        </div>
        <Button onclick={() => (dialogOpen = true)}>
          <Plus class="size-4" /> Add your first key
        </Button>
      </CardContent>
    </Card>
  {:else}
    <Card class="animate-fade-up overflow-hidden" style="animation-delay: 60ms">
      <CardContent class="p-0">
        <ul class="divide-y divide-border">
          {#each data.keys as k, i (k.id)}
            {@const algo = keyAlgo(k.public_key)}
            <li
              class="group flex items-center gap-3.5 p-4 transition-colors hover:bg-muted/40"
              style="animation: fade-up 0.5s cubic-bezier(0.16,1,0.3,1) both; animation-delay: {80 + i * 45}ms"
            >
              <div
                class="grid size-9 shrink-0 place-items-center rounded-lg ring-1 ring-inset transition-transform group-hover:scale-105 {algo.tint}"
              >
                <KeyRound class="size-4" strokeWidth={1.75} />
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="min-w-0 break-all font-medium">{k.name}</span>
                  <span
                    class="shrink-0 rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold tracking-wide ring-1 ring-inset {algo.tint}"
                  >
                    {algo.label}
                  </span>
                  <Badge variant="muted" class="shrink-0">added {relTime(k.created_at)}</Badge>
                </div>
                <div class="mt-1.5 flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
                  <Fingerprint class="size-3 shrink-0" />
                  <code class="min-w-0 truncate font-mono">{k.fingerprint}</code>
                </div>
              </div>
              <div
                class="flex shrink-0 items-center gap-1 opacity-60 transition-opacity group-hover:opacity-100"
              >
                <Tooltip content="Copy fingerprint">
                  {#snippet children(props)}
                  <Button
                    {...props}
                    variant="ghost"
                    size="icon"
                    onclick={() => copyFingerprint(k.fingerprint)}
                  >
                    <Copy class="size-3.5" />
                  </Button>
                  {/snippet}
                </Tooltip>
                <Tooltip content="Remove key">
                  {#snippet children(props)}
                  <Button
                    {...props}
                    variant="ghost"
                    size="icon"
                    class="hover:bg-destructive/10"
                    onclick={() => deleteKey(k)}
                  >
                    <Trash2 class="size-3.5 text-destructive" />
                  </Button>
                  {/snippet}
                </Tooltip>
              </div>
            </li>
          {/each}
        </ul>
      </CardContent>
    </Card>
  {/if}

  <!-- Help: finding your public key -->
  <Card class="animate-fade-up overflow-hidden" style="animation-delay: 120ms">
    <div class="flex items-center gap-2.5 border-b border-border bg-muted/40 px-4 py-3">
      <Terminal class="size-4 text-muted-foreground" strokeWidth={1.75} />
      <span class="text-sm font-medium">How to find your public key</span>
      <Tooltip content="Copy commands">
        {#snippet children(props)}
        <Button
          {...props}
          variant="ghost"
          size="icon"
          class="ml-auto size-7 opacity-70 transition-opacity hover:opacity-100"
          onclick={copySnippet}
        >
          <Copy class="size-3.5" />
        </Button>
        {/snippet}
      </Tooltip>
    </div>
    <CardContent class="space-y-3.5 p-5 text-sm text-muted-foreground">
      <p>On macOS / Linux, run:</p>
      <pre
        class="overflow-x-auto rounded-lg border border-border bg-muted/30 p-4 font-mono text-xs leading-relaxed text-foreground/90"
        >{KEYGEN_SNIPPET}</pre>
      <p class="flex items-start gap-2">
        <Check class="mt-0.5 size-3.5 shrink-0 text-success" />
        Paste the public key (the file ending in <code class="rounded bg-muted px-1 font-mono text-xs">.pub</code>) above. Never paste your private key.
      </p>
    </CardContent>
  </Card>

  <!-- API keys — programmatic access tokens -->
  <div class="animate-fade-up space-y-3 pt-2" style="animation-delay: 160ms">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Fingerprint class="size-[1.15rem] text-muted-foreground" strokeWidth={1.75} />
          API keys
        </h2>
        <p class="mt-0.5 text-sm text-muted-foreground">
          Tokens for scripts and CI — sent as a bearer token. The secret is shown once, at creation.
        </p>
      </div>
      <Button variant="outline" onclick={() => (apiDialogOpen = true)}>
        <Plus class="size-4" /> New API key
      </Button>
    </div>

    {#if data.apiKeys.length === 0}
      <Card class="border-dashed bg-muted/20">
        <CardContent class="py-10 text-center text-sm text-muted-foreground">
          No API keys yet. Create one to call the Hopper API from scripts.
        </CardContent>
      </Card>
    {:else}
      <Card class="overflow-hidden">
        <ul class="divide-y divide-border">
          {#each data.apiKeys as k (k.id)}
            <li class="group flex items-center gap-3.5 p-4 transition-colors hover:bg-muted/40 {k.revoked_at ? 'opacity-55' : ''}">
              <div class="grid size-9 shrink-0 place-items-center rounded-lg bg-info/10 text-info ring-1 ring-inset ring-info/20">
                <Fingerprint class="size-4" strokeWidth={1.75} />
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="min-w-0 break-all font-medium">{k.name}</span>
                  <code class="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">{k.prefix}…</code>
                  <Badge variant={k.scope === 'full_access' ? 'warning' : 'muted'} class="shrink-0">
                    {k.scope === 'full_access' ? 'Full access' : 'Read-only'}
                  </Badge>
                  {#if k.revoked_at}
                    <Badge variant="destructive" class="shrink-0">Revoked</Badge>
                  {/if}
                </div>
                <div class="mt-1 text-xs text-muted-foreground">
                  Created {relTime(k.created_at)}
                  · {k.last_used_at ? `last used ${relTime(k.last_used_at)}` : 'never used'}
                </div>
              </div>
              {#if !k.revoked_at}
                <Tooltip content="Revoke key">
                  {#snippet children(props)}
                  <Button
                    {...props}
                    variant="ghost"
                    size="icon"
                    class="shrink-0 opacity-60 transition-opacity hover:bg-destructive/10 group-hover:opacity-100"
                    onclick={() => revokeApiKey(k)}
                  >
                    <Trash2 class="size-3.5 text-destructive" />
                  </Button>
                  {/snippet}
                </Tooltip>
              {/if}
            </li>
          {/each}
        </ul>
      </Card>
    {/if}
  </div>
</div>

<Dialog
  bind:open={dialogOpen}
  title="Add a new SSH key"
  description="Public keys are stored in our database and pushed to your VMs at launch."
>
  <div class="space-y-4">
    <div>
      <Label for="name">Key name</Label>
      <Input
        id="name"
        bind:value={newName}
        placeholder="My laptop"
        class="mt-1"
      />
    </div>
    <div>
      <Label for="key">Public key</Label>
      <Textarea
        id="key"
        bind:value={newKey}
        rows={6}
        placeholder="ssh-ed25519 AAAA… you@example.edu"
        class="mt-1 font-mono text-xs"
      />
      <p class="mt-1.5 text-xs text-muted-foreground">
        Must start with <code class="font-mono">ssh-rsa</code>, <code class="font-mono">ssh-ed25519</code>,
        <code class="font-mono">ecdsa-sha2</code>, or <code class="font-mono">ssh-dss</code>.
      </p>
    </div>
  </div>

  {#snippet footer()}
    <Button
      variant="outline"
      onclick={() => {
        dialogOpen = false;
        reset();
      }}
    >
      Cancel
    </Button>
    <Button onclick={addKey} disabled={saving}>
      {#if saving}
        <Spinner class="size-4" /> Saving…
      {:else}
        <Plus class="size-4" /> Add key
      {/if}
    </Button>
  {/snippet}
</Dialog>

<!-- Create API key -->
<Dialog
  bind:open={apiDialogOpen}
  title="Create an API key"
  description="Use it as a bearer token from scripts or CI. The secret is shown only once."
>
  {#if createdToken}
    <div class="space-y-3">
      <div class="rounded-lg border border-warning/30 bg-warning/5 px-3 py-2.5 text-xs text-muted-foreground">
        Copy this token now — it won't be shown again. Only a hash is stored server-side.
      </div>
      <div class="relative">
        <code class="block w-full select-all overflow-x-auto whitespace-nowrap rounded-lg border border-border bg-muted/50 py-2.5 pl-3 pr-11 font-mono text-xs">
          {createdToken}
        </code>
        <button
          class="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
          onclick={copyToken}
          aria-label="Copy token"
          title="Copy token"
        >
          <Copy class="size-3.5" />
        </button>
      </div>
    </div>
  {:else}
    <div class="space-y-4">
      <div>
        <Label for="ak-name">Key name</Label>
        <Input id="ak-name" bind:value={apiKeyName} placeholder="CI pipeline" class="mt-1" />
      </div>
      <div>
        <Label>Scope</Label>
        <div class="mt-1.5 grid gap-2 sm:grid-cols-2">
          {#each [
            { value: 'read_only', label: 'Read-only', desc: 'GET requests only — safe for dashboards.' },
            { value: 'full_access', label: 'Full access', desc: 'Can launch and terminate VMs.' }
          ] as opt (opt.value)}
            <button
              type="button"
              class={`rounded-xl border p-3 text-left transition-colors ${
                apiKeyScope === opt.value
                  ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                  : 'border-border hover:border-primary/40'
              }`}
              onclick={() => (apiKeyScope = opt.value as 'read_only' | 'full_access')}
            >
              <div class="text-sm font-medium">{opt.label}</div>
              <div class="mt-0.5 text-xs text-muted-foreground">{opt.desc}</div>
            </button>
          {/each}
        </div>
      </div>
    </div>
  {/if}
  {#snippet footer()}
    {#if createdToken}
      <Button
        onclick={() => {
          createdToken = null;
          apiDialogOpen = false;
        }}
      >
        Done
      </Button>
    {:else}
      <Button variant="outline" onclick={() => (apiDialogOpen = false)}>Cancel</Button>
      <Button onclick={createApiKey} disabled={apiKeySaving}>
        {#if apiKeySaving}
          <Spinner class="size-4" /> Creating…
        {:else}
          <Plus class="size-4" /> Create key
        {/if}
      </Button>
    {/if}
  {/snippet}
</Dialog>
