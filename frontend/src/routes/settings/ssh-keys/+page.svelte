<script lang="ts">
  import {
    KeyRound,
    Plus,
    Trash2,
    Copy,
    Fingerprint,
    Loader2,
    ShieldCheck,
    Terminal,
    Check
  } from 'lucide-svelte';
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
    Tooltip,
    Separator
  } from '$lib/ui';
  import { api, ApiError } from '$lib/api/client';
  import PageTitle from '$lib/components/PageTitle.svelte';
  import { confirm } from '$lib/confirm.svelte';
  import { copyToClipboard, relTime } from '$lib/utils';
  import type { SshKey } from '$lib/types';

  let { data }: { data: { keys: SshKey[] } } = $props();

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
        'Public key looks invalid — should start with ssh-rsa, ssh-ed25519, ecdsa-sha2, or ssh-dss'
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
</script>

<div class="space-y-5">
  <PageTitle
    title="SSH keys"
    eyebrow="Settings"
    eyebrowIcon={KeyRound}
    description="Public keys registered here are pushed to every VM you launch — enabling passwordless SSH from any device whose private key matches."
  >
    {#snippet action()}
      <Button onclick={() => (dialogOpen = true)} disabled={data.keys.length >= MAX_KEYS}>
        <Plus class="size-4" /> Add SSH key
      </Button>
    {/snippet}
  </PageTitle>

  <!-- Capacity panel — segmented slot meter for the per-account key limit. -->
  <Card class="animate-fade-up surface-glow overflow-hidden">
    <CardContent class="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-center gap-3">
        <div
          class="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-info text-white shadow-sm shadow-primary/20"
        >
          <ShieldCheck class="size-5" />
        </div>
        <div>
          <div class="flex items-baseline gap-1.5">
            <span class="text-xl font-bold tracking-tight tabular-nums">{data.keys.length}</span>
            <span class="text-sm text-muted-foreground">of {MAX_KEYS} keys used</span>
          </div>
          <p class="text-sm text-muted-foreground">
            {#if atLimit}
              You've reached the limit — remove one to add another.
            {:else}
              {MAX_KEYS - data.keys.length} slot{MAX_KEYS - data.keys.length === 1 ? '' : 's'} remaining on your account.
            {/if}
          </p>
        </div>
      </div>
      <div class="w-full sm:w-64">
        <div class="flex items-center gap-1.5">
          {#each { length: MAX_KEYS } as _, i (i)}
            <span
              class={`h-2.5 flex-1 rounded-full transition-all duration-500 ${
                i < data.keys.length
                  ? atLimit
                    ? 'bg-gradient-to-r from-warning to-destructive'
                    : 'bg-gradient-to-r from-primary to-info'
                  : 'bg-muted'
              }`}
              style="transition-delay: {i * 35}ms"
            ></span>
          {/each}
        </div>
        <div class="mt-2 flex items-center justify-between text-xs font-medium">
          <span class="text-muted-foreground">{data.keys.length} used · {MAX_KEYS - data.keys.length} free</span>
          <span class={atLimit ? 'text-destructive' : 'text-muted-foreground'}>{Math.round(usedPct)}% full</span>
        </div>
      </div>
    </CardContent>
  </Card>

  {#if data.keys.length === 0}
    <Card class="animate-fade-up surface-glow overflow-hidden border-dashed" style="animation-delay: 60ms">
      <CardContent class="relative flex flex-col items-center gap-4 py-14 text-center">
        <!-- soft glow behind the key mark -->
        <div class="relative flex items-center justify-center">
          <span class="halo pointer-events-none absolute size-20 rounded-full bg-primary/20 blur-2xl"></span>
          <div
            class="relative flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-info text-white shadow-lg shadow-primary/30"
          >
            <KeyRound class="size-6" />
          </div>
        </div>
        <div>
          <p class="text-base font-semibold">No keys registered yet</p>
          <p class="mt-1.5 max-w-sm text-sm leading-relaxed text-muted-foreground">
            Add your laptop's public key (usually <code
              class="rounded bg-muted px-1 py-0.5 font-mono text-xs">~/.ssh/id_ed25519.pub</code
            >) so you can SSH into VMs without typing the root password.
          </p>
        </div>
        <Button onclick={() => (dialogOpen = true)} class="shadow-md shadow-primary/20">
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
              class="group flex items-center gap-3 p-3 transition-colors hover:bg-muted/40"
              style="animation: fade-up 0.5s cubic-bezier(0.16,1,0.3,1) both; animation-delay: {80 + i * 45}ms"
            >
              <div
                class="flex size-9 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset transition-transform group-hover:scale-105 {algo.tint}"
              >
                <KeyRound class="size-4" />
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
                <div class="mt-1 flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
                  <Fingerprint class="size-3 shrink-0" />
                  <code class="min-w-0 truncate font-mono">{k.fingerprint}</code>
                </div>
              </div>
              <div
                class="flex shrink-0 items-center gap-1 opacity-60 transition-opacity group-hover:opacity-100"
              >
                <Tooltip content="Copy fingerprint">
                  <Button
                    variant="ghost"
                    size="icon"
                    onclick={() => copyFingerprint(k.fingerprint)}
                  >
                    <Copy class="size-3.5" />
                  </Button>
                </Tooltip>
                <Tooltip content="Remove key">
                  <Button
                    variant="ghost"
                    size="icon"
                    class="hover:bg-destructive/10"
                    onclick={() => deleteKey(k)}
                  >
                    <Trash2 class="size-3.5 text-destructive" />
                  </Button>
                </Tooltip>
              </div>
            </li>
          {/each}
        </ul>
      </CardContent>
    </Card>
  {/if}

  <!-- Help — styled as a terminal window -->
  <Card class="animate-fade-up overflow-hidden" style="animation-delay: 120ms">
    <div class="flex items-center gap-2 border-b border-border bg-muted/40 px-3.5 py-2.5">
      <div class="flex gap-1.5">
        <span class="size-3 rounded-full bg-destructive/60"></span>
        <span class="size-3 rounded-full bg-warning/60"></span>
        <span class="size-3 rounded-full bg-success/60"></span>
      </div>
      <span class="ml-1.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Terminal class="size-3.5" /> How to find your public key
      </span>
      <Tooltip content="Copy commands">
        <Button
          variant="ghost"
          size="icon"
          class="ml-auto size-7 opacity-70 transition-opacity hover:opacity-100"
          onclick={copySnippet}
        >
          <Copy class="size-3.5" />
        </Button>
      </Tooltip>
    </div>
    <CardContent class="space-y-3 p-4 text-sm text-muted-foreground">
      <p>On macOS / Linux, run:</p>
      <pre
        class="overflow-x-auto rounded-lg border border-border bg-muted/30 p-3 font-mono text-xs leading-relaxed text-foreground/90"
        >{KEYGEN_SNIPPET}</pre>
      <p class="flex items-start gap-1.5">
        <Check class="mt-0.5 size-3.5 shrink-0 text-success" />
        Paste the public key (the file ending in <code class="rounded bg-muted px-1 font-mono text-xs">.pub</code>) above. Never paste your private key.
      </p>
    </CardContent>
  </Card>
</div>

<style>
  /* Gentle breathing halo behind the empty-state key mark. */
  .halo {
    animation: halo 3.2s ease-in-out infinite;
  }
  @keyframes halo {
    0%,
    100% {
      opacity: 0.45;
      transform: scale(1);
    }
    50% {
      opacity: 0.9;
      transform: scale(1.06);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .halo {
      animation: none;
    }
  }
</style>

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
        <Loader2 class="size-4 animate-spin" /> Saving…
      {:else}
        <Plus class="size-4" /> Add key
      {/if}
    </Button>
  {/snippet}
</Dialog>
