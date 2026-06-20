<script lang="ts">
  import {
    KeyRound,
    Plus,
    Trash2,
    Copy,
    Fingerprint,
    Loader2,
    ShieldCheck
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

<div class="space-y-8">
  <PageTitle
    title="SSH keys"
    eyebrow="Settings"
    eyebrowIcon={KeyRound}
    description="Public keys registered here are pushed to every VM you launch — enabling passwordless SSH from any device whose private key matches."
  />

  <Card>
    <CardContent class="flex flex-col gap-3 pt-6 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-center gap-3">
        <div class="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <ShieldCheck class="size-5" />
        </div>
        <div>
          <div class="font-medium">{data.keys.length} of 10 keys</div>
          <p class="text-sm text-muted-foreground">
            Maximum of 10 keys per account.
          </p>
        </div>
      </div>
      <Button onclick={() => (dialogOpen = true)} disabled={data.keys.length >= 10}>
        <Plus class="size-4" /> Add SSH key
      </Button>
    </CardContent>
  </Card>

  {#if data.keys.length === 0}
    <Card class="border-dashed bg-muted/20">
      <CardContent class="flex flex-col items-center gap-3 py-12 text-center">
        <div
          class="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary"
        >
          <KeyRound class="size-5" />
        </div>
        <div>
          <p class="font-medium">No keys registered yet</p>
          <p class="mt-1 max-w-sm text-sm text-muted-foreground">
            Add your laptop's public key (usually <code
              class="font-mono text-xs">~/.ssh/id_ed25519.pub</code
            >) so you can SSH into VMs without typing the root password.
          </p>
        </div>
        <Button onclick={() => (dialogOpen = true)}>
          <Plus class="size-4" /> Add your first key
        </Button>
      </CardContent>
    </Card>
  {:else}
    <Card>
      <CardContent class="p-0">
        <ul class="divide-y divide-border">
          {#each data.keys as k (k.id)}
            <li class="flex items-center gap-4 p-4">
              <div
                class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground"
              >
                <KeyRound class="size-4" />
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="font-medium">{k.name}</span>
                  <Badge variant="muted">added {relTime(k.created_at)}</Badge>
                </div>
                <div class="mt-1 flex items-center gap-1 truncate text-xs text-muted-foreground">
                  <Fingerprint class="size-3" />
                  <code class="truncate font-mono">{k.fingerprint}</code>
                </div>
              </div>
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
                <Button variant="ghost" size="icon" onclick={() => deleteKey(k)}>
                  <Trash2 class="size-3.5 text-destructive" />
                </Button>
              </Tooltip>
            </li>
          {/each}
        </ul>
      </CardContent>
    </Card>
  {/if}

  <Card class="border-border/60 bg-muted/20">
    <CardContent class="space-y-2 pt-6 text-sm text-muted-foreground">
      <div class="font-semibold text-foreground">How to find your public key</div>
      <p>On macOS / Linux, run:</p>
      <pre
        class="overflow-x-auto rounded-md border border-border bg-card p-3 font-mono text-xs"
        ># Generate a new ed25519 key (skip if you already have one)
ssh-keygen -t ed25519 -C "you@example.edu"

# Copy the PUBLIC key to clipboard
cat ~/.ssh/id_ed25519.pub | pbcopy   # macOS
cat ~/.ssh/id_ed25519.pub | xclip    # Linux</pre>
      <p>Paste the public key (the file ending in <code>.pub</code>) above. Never paste your private key.</p>
    </CardContent>
  </Card>
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
        <Loader2 class="size-4 animate-spin" /> Saving…
      {:else}
        <Plus class="size-4" /> Add key
      {/if}
    </Button>
  {/snippet}
</Dialog>
