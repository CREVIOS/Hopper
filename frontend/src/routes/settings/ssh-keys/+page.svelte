<script lang="ts">
  import {
    KeyRound,
    Plus,
    Trash2,
    Copy,
    Fingerprint,
    ShieldCheck,
    Terminal,
    Check,
    AlertTriangle
  } from 'lucide-svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { invalidateAll, goto } from '$app/navigation';
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

  // `user` is merged in from the root layout load (email is needed to confirm
  // account deletion below).
  let { data }: { data: { keys: SshKey[]; user?: { email?: string } | null } } = $props();

  const MAX_KEYS = 10;
  const usedPct = $derived((data.keys.length / MAX_KEYS) * 100);
  const atLimit = $derived(data.keys.length >= MAX_KEYS);

  // --- Account deletion (danger zone) ---
  let deleteOpen = $state(false);
  let confirmEmail = $state('');
  let deleting = $state(false);
  const accountEmail = $derived(data.user?.email ?? '');
  // The confirm button only enables once the typed email matches the account.
  const confirmMatches = $derived(
    accountEmail.length > 0 && confirmEmail.trim().toLowerCase() === accountEmail.toLowerCase()
  );

  async function deleteAccount() {
    if (!confirmMatches || deleting) return;
    deleting = true;
    const id = toast.loading('Deleting your account…');
    try {
      await api.delete('/auth/me', { confirm_email: confirmEmail.trim() });
      toast.success('Account deleted', { id, description: 'Signing you out…' });
      // Cookies are cleared by the backend; send the user to login.
      await goto('/login');
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Could not delete account';
      toast.error('Deletion failed', { id, description: msg });
      deleting = false;
    }
  }

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
</div>

<!-- Danger zone: irreversible account deletion. -->
<div class="mt-8">
  <Card class="overflow-hidden border-destructive/40">
    <div class="flex items-start gap-3 border-b border-destructive/30 bg-destructive/5 px-5 py-4">
      <span class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
        <AlertTriangle class="size-4" />
      </span>
      <div>
        <h3 class="text-sm font-semibold text-destructive">Danger zone</h3>
        <p class="text-xs text-muted-foreground">Irreversible account actions.</p>
      </div>
    </div>
    <CardContent class="flex flex-col gap-3 py-5 sm:flex-row sm:items-center sm:justify-between">
      <div class="text-sm">
        <p class="font-medium">Delete your account</p>
        <p class="text-xs text-muted-foreground">
          Terminates your VMs and permanently removes your login, SSH keys, settings, and
          workspace. Your billing history is retained. This cannot be undone.
        </p>
      </div>
      <Button
        variant="destructive"
        class="shrink-0"
        onclick={() => {
          confirmEmail = '';
          deleteOpen = true;
        }}
      >
        <Trash2 class="size-4" /> Delete account
      </Button>
    </CardContent>
  </Card>
</div>

<Dialog bind:open={deleteOpen} title="Delete your account?" description="This action is permanent and cannot be undone.">
  <div class="space-y-4">
    <div class="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-muted-foreground">
      <AlertTriangle class="mt-0.5 size-4 shrink-0 text-destructive" />
      <span>
        Your running VMs will be terminated and your login, SSH keys, settings, and workspace
        will be permanently deleted. Your credit/billing history is retained for records.
      </span>
    </div>
    <div>
      <Label for="confirm-email">
        Type <span class="font-mono font-medium text-foreground">{accountEmail}</span> to confirm
      </Label>
      <Input
        id="confirm-email"
        bind:value={confirmEmail}
        placeholder={accountEmail}
        class="mt-1 font-mono"
        autocomplete="off"
      />
    </div>
  </div>

  {#snippet footer()}
    <Button variant="outline" onclick={() => (deleteOpen = false)} disabled={deleting}>Cancel</Button>
    <Button variant="destructive" onclick={deleteAccount} disabled={!confirmMatches || deleting}>
      {#if deleting}
        <Spinner class="size-4" /> Deleting…
      {:else}
        <Trash2 class="size-4" /> Delete my account
      {/if}
    </Button>
  {/snippet}
</Dialog>

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
