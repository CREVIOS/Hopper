<script lang="ts">
  import {
    Upload,
    Download,
    File as FileIcon,
    Folder,
    FolderOpen,
    Trash2,
    ChevronRight,
    RefreshCw,
    Home as HomeIcon,
    AlertCircle,
    CornerLeftUp
  } from 'lucide-svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { toast } from 'svelte-sonner';
  import { Button, Card, Input, Label } from '$lib/ui';
  import { api, ApiError } from '$lib/api/client';
  import { formatBytes, relTime } from '$lib/utils';

  let { podId, podRunning }: { podId: string; podRunning: boolean } = $props();

  type Recent = { name: string; size: number; dest: string; at: Date };
  type Entry = { name: string; is_dir: boolean; size: number; mtime: string };

  // The browser is the single source of truth for paths the user is acting on.
  // Free-text inputs default to the current directory, so a click in the
  // browser pre-fills both upload destination and download path.
  const HOME = '/root';
  let cwd = $state(HOME);
  let entries = $state<Entry[]>([]);
  let listing = $state(false);
  let listError = $state<string | null>(null);

  let destPath = $state(HOME);
  let downloadPath = $state('');
  let dragOver = $state(false);
  let uploading = $state(false);
  let downloading = $state(false);
  let recent = $state<Recent[]>([]);

  // Path validator: must be absolute, no null bytes, no double-slash. The
  // backend also enforces this, but inline feedback is faster than waiting
  // for a 400 round-trip.
  function pathError(p: string): string | null {
    if (!p.trim()) return 'Path is required';
    if (!p.startsWith('/')) return 'Path must be absolute (start with /)';
    if (p.includes('//')) return 'Path contains an empty segment (//)';
    if (/[\x00\n\r]/.test(p)) return 'Path contains an invalid character';
    return null;
  }
  const destErr = $derived(pathError(destPath));
  const dlErr = $derived(downloadPath ? pathError(downloadPath) : null);

  async function loadDir(path: string) {
    if (!podRunning) return;
    listing = true;
    listError = null;
    try {
      const data = await api.get<{ path: string; entries: Entry[] }>(
        `/files/${podId}/list?path=${encodeURIComponent(path)}`
      );
      cwd = data.path;
      entries = data.entries;
      destPath = data.path; // mirror browser state into upload form
    } catch (e) {
      listError = e instanceof ApiError ? e.message : 'Could not list directory';
      entries = [];
    } finally {
      listing = false;
    }
  }

  function navigate(name: string) {
    const next = cwd === '/' ? `/${name}` : `${cwd}/${name}`;
    loadDir(next);
  }

  function navigateUp() {
    if (cwd === '/') return;
    const parts = cwd.split('/').filter(Boolean);
    parts.pop();
    loadDir(parts.length ? `/${parts.join('/')}` : '/');
  }

  function pickForDownload(entry: Entry) {
    if (entry.is_dir) return;
    downloadPath = cwd === '/' ? `/${entry.name}` : `${cwd}/${entry.name}`;
  }

  $effect(() => {
    if (podRunning && entries.length === 0 && !listing && !listError) {
      loadDir(HOME);
    }
  });

  async function uploadFile(file: File) {
    if (uploading) return;
    if (!podRunning) {
      toast.error('VM is not running');
      return;
    }
    if (destErr) {
      toast.error(destErr);
      return;
    }
    uploading = true;
    const id = toast.loading(`Uploading ${file.name}…`);
    const form = new FormData();
    form.append('file', file);
    try {
      const dest = destPath.trim();
      await api.upload(
        `/files/${podId}/upload?dest_path=${encodeURIComponent(dest)}`,
        form
      );
      recent = [
        { name: file.name, size: file.size, dest, at: new Date() },
        ...recent
      ].slice(0, 8);
      toast.success(`Uploaded ${file.name}`, { id, description: `→ ${dest}` });
      // Refresh the browser if we uploaded into the current directory.
      if (dest === cwd) loadDir(cwd);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Upload failed';
      toast.error('Upload failed', { id, description: msg });
    } finally {
      uploading = false;
    }
  }

  async function handleFileInput(e: Event) {
    const input = e.target as HTMLInputElement;
    const f = input.files?.[0];
    if (f) await uploadFile(f);
    input.value = '';
  }

  async function handleDrop(e: DragEvent) {
    e.preventDefault();
    dragOver = false;
    const f = e.dataTransfer?.files?.[0];
    if (f) await uploadFile(f);
  }

  async function downloadFile() {
    const path = downloadPath.trim();
    if (dlErr || !path) {
      toast.error(dlErr ?? 'Enter a path');
      return;
    }
    if (!podRunning) {
      toast.error('VM is not running');
      return;
    }
    downloading = true;
    const id = toast.loading(`Downloading ${path}…`);
    try {
      const blob = await api.download(
        `/files/${podId}/download?path=${encodeURIComponent(path)}`
      );
      const filename = path.split('/').filter(Boolean).pop() ?? 'download';
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success('Download started', { id });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Download failed';
      toast.error('Download failed', { id, description: msg });
    } finally {
      downloading = false;
    }
  }

  function clearRecent(item: Recent) {
    recent = recent.filter((r) => r !== item);
  }

  // Render the breadcrumb as clickable parts.
  const breadcrumbs = $derived.by(() => {
    const parts = cwd.split('/').filter(Boolean);
    const acc: { label: string; path: string }[] = [{ label: '/', path: '/' }];
    let curr = '';
    for (const p of parts) {
      curr += `/${p}`;
      acc.push({ label: p, path: curr });
    }
    return acc;
  });
</script>

<!-- Directory browser — gives users concrete paths to click instead of guessing. -->
<Card class="mb-4 overflow-hidden">
  <!-- Header -->
  <div class="flex flex-wrap items-center justify-between gap-2 px-5 pb-3 pt-5">
    <h3 class="flex items-center gap-2.5 text-sm font-semibold">
      <span
        class="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary"
      >
        <FolderOpen class="size-4" />
      </span>
      VM file browser
    </h3>
    <div class="flex items-center gap-1.5">
      <Button
        variant="outline"
        size="sm"
        onclick={() => loadDir(HOME)}
        disabled={!podRunning || listing}
      >
        <HomeIcon class="size-3.5" /> Home
      </Button>
      <Button
        variant="outline"
        size="sm"
        onclick={() => loadDir(cwd)}
        disabled={!podRunning || listing}
      >
        <RefreshCw class="size-3.5 {listing ? 'animate-spin' : ''}" /> Refresh
      </Button>
    </div>
  </div>

  <!-- Breadcrumb toolbar -->
  <nav
    class="flex flex-wrap items-center gap-0.5 border-y border-border/60 bg-muted/30 px-4 py-2 font-mono text-xs"
  >
    {#each breadcrumbs as crumb, i (crumb.path)}
      {#if i > 0}
        <ChevronRight class="size-3 text-muted-foreground/60" />
      {/if}
      <button
        class="rounded-md px-1.5 py-0.5 transition-colors hover:bg-accent hover:text-foreground disabled:cursor-default disabled:font-semibold disabled:text-foreground"
        onclick={() => loadDir(crumb.path)}
        disabled={crumb.path === cwd}
        aria-label={i === 0 ? 'Root' : crumb.label}
      >
        {#if i === 0}
          <HomeIcon class="-mt-0.5 inline size-3" />
        {:else}
          {crumb.label}
        {/if}
      </button>
    {/each}
  </nav>

  {#if !podRunning}
    <p class="px-5 py-12 text-center text-sm text-muted-foreground">
      Start the VM to browse its files.
    </p>
  {:else if listError}
    <div class="px-5 py-4">
      <div
        class="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
      >
        <AlertCircle class="mt-0.5 size-4 shrink-0" />
        <span>{listError}</span>
      </div>
    </div>
  {:else if listing && entries.length === 0}
    <p class="px-5 py-12 text-center text-sm text-muted-foreground">Loading…</p>
  {:else}
    <!-- Scrollable list — capped so heavy directories can't grow the card unbounded. -->
    <div class="max-h-[20rem] overflow-y-auto">
      <ul class="divide-y divide-border/60">
        {#if cwd !== '/'}
          <li>
            <button
              class="flex w-full items-center gap-2.5 px-5 py-2 text-left text-sm transition-colors hover:bg-muted/50"
              onclick={navigateUp}
            >
              <CornerLeftUp class="size-4 text-muted-foreground" />
              <span class="font-mono">..</span>
              <span class="text-xs text-muted-foreground">Up one level</span>
            </button>
          </li>
        {/if}
        {#each entries as entry (entry.name)}
          <li class="group flex items-center gap-2.5 px-5 py-2 transition-colors hover:bg-muted/50">
            <button
              class="flex min-w-0 flex-1 items-center gap-2.5 text-left text-sm"
              onclick={() => (entry.is_dir ? navigate(entry.name) : pickForDownload(entry))}
              title={entry.is_dir ? `Open ${entry.name}` : `Select ${entry.name} for download`}
            >
              {#if entry.is_dir}
                <span class="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <Folder class="size-3.5" />
                </span>
              {:else}
                <span class="flex size-6 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                  <FileIcon class="size-3.5" />
                </span>
              {/if}
              <span class="truncate font-mono transition-colors group-hover:text-primary">
                {entry.name}{entry.is_dir ? '/' : ''}
              </span>
            </button>
            <span class="shrink-0 font-mono text-xs text-muted-foreground">
              {entry.is_dir ? '' : formatBytes(entry.size)}
            </span>
          </li>
        {:else}
          <li class="px-5 py-12 text-center text-xs text-muted-foreground">
            Empty directory.
          </li>
        {/each}
      </ul>
    </div>
    <div class="border-t border-border/60 px-5 py-2.5 text-xs text-muted-foreground">
      Click a folder to open it, a file to select it for download. Uploads go to the current path.
    </div>
  {/if}
</Card>

<div class="grid gap-4 lg:grid-cols-2">
  <!-- Upload -->
  <Card class="overflow-hidden">
    <div class="flex items-center gap-2.5 px-5 pb-3 pt-5">
      <span class="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Upload class="size-4" />
      </span>
      <div>
        <h3 class="text-sm font-semibold">Upload to VM</h3>
        <p class="text-xs text-muted-foreground">Pushed over SCP to the destination below.</p>
      </div>
    </div>

    <div class="space-y-4 border-t border-border/60 px-5 py-5">
      <div class="space-y-1.5">
        <Label for="dest-path">Destination directory</Label>
        <Input
          id="dest-path"
          bind:value={destPath}
          placeholder="/root"
          class="font-mono {destErr ? 'border-destructive' : ''}"
          aria-invalid={!!destErr}
          aria-describedby={destErr ? 'dest-err' : undefined}
        />
        {#if destErr}
          <p id="dest-err" class="text-xs text-destructive">{destErr}</p>
        {:else}
          <p class="text-xs text-muted-foreground">
            Existing directory inside the VM, e.g. <code class="font-mono">/root</code>
            or <code class="font-mono">/workspace</code>.
          </p>
        {/if}
      </div>

      <label
        class="group flex cursor-pointer flex-col items-center justify-center gap-2.5 rounded-xl border-2 border-dashed p-7 text-center transition-all {dragOver
          ? 'border-primary bg-primary/5'
          : 'border-border hover:border-primary/50 hover:bg-muted/30'}"
        ondragover={(e) => {
          e.preventDefault();
          dragOver = true;
        }}
        ondragleave={() => (dragOver = false)}
        ondrop={handleDrop}
      >
        {#if uploading}
          <span class="flex size-11 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Spinner class="size-5" />
          </span>
          <span class="text-sm font-medium text-muted-foreground">Uploading…</span>
        {:else}
          <span class="flex size-11 items-center justify-center rounded-full bg-primary/10 text-primary transition-transform group-hover:scale-105">
            <Upload class="size-5" />
          </span>
          <span class="text-sm font-medium">
            Drop a file or <span class="text-primary">click to browse</span>
          </span>
          <span class="text-xs text-muted-foreground">
            Single file. Max size depends on your gateway config.
          </span>
        {/if}
        <input
          type="file"
          class="hidden"
          disabled={uploading || !podRunning || !!destErr}
          onchange={handleFileInput}
        />
      </label>

      <div
        class="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2.5 text-xs text-muted-foreground"
      >
        <AlertCircle class="mt-0.5 size-3.5 shrink-0 text-warning" />
        <span>
          Paths inside the VM are <span class="font-medium text-foreground">ephemeral</span> —
          wiped when the VM terminates. Persistent
          <code class="rounded bg-muted px-1 py-0.5 font-mono">/workspace</code> is on the roadmap.
        </span>
      </div>
    </div>
  </Card>

  <!-- Download -->
  <Card class="overflow-hidden">
    <div class="flex items-center gap-2.5 px-5 pb-3 pt-5">
      <span class="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Download class="size-4" />
      </span>
      <div>
        <h3 class="text-sm font-semibold">Download from VM</h3>
        <p class="text-xs text-muted-foreground">Pick a file above, or paste an absolute path.</p>
      </div>
    </div>

    <div class="space-y-4 border-t border-border/60 px-5 py-5">
      <div class="space-y-1.5">
        <Label for="dl-path">File path</Label>
        <Input
          id="dl-path"
          bind:value={downloadPath}
          placeholder="/root/output.txt"
          class="font-mono {dlErr ? 'border-destructive' : ''}"
          aria-invalid={!!dlErr}
          aria-describedby={dlErr ? 'dl-err' : undefined}
        />
        {#if dlErr}
          <p id="dl-err" class="text-xs text-destructive">{dlErr}</p>
        {/if}
      </div>
      <Button
        onclick={downloadFile}
        disabled={downloading || !podRunning || !downloadPath || !!dlErr}
        class="w-full"
      >
        {#if downloading}
          <Spinner class="size-4" /> Downloading…
        {:else}
          <Download class="size-4" /> Download
        {/if}
      </Button>
    </div>
  </Card>
</div>

{#if recent.length > 0}
  <Card class="mt-4 overflow-hidden">
    <div class="flex items-center gap-2.5 px-5 pb-3 pt-5">
      <span class="flex size-8 items-center justify-center rounded-lg bg-success/10 text-success">
        <Upload class="size-4" />
      </span>
      <h3 class="text-sm font-semibold">Recent uploads</h3>
      <span class="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
        this session
      </span>
    </div>
    <div class="max-h-[16rem] overflow-y-auto border-t border-border/60">
      <ul class="divide-y divide-border/60">
        {#each recent as item (item.at.toISOString() + item.name)}
          <li class="group flex items-center gap-3 px-5 py-2.5 transition-colors hover:bg-muted/40">
            <span class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              <FileIcon class="size-4" />
            </span>
            <div class="min-w-0 flex-1">
              <div class="truncate font-mono text-sm">{item.name}</div>
              <div class="truncate text-xs text-muted-foreground">
                {formatBytes(item.size)} · {item.dest} · {relTime(item.at)}
              </div>
            </div>
            <button
              class="rounded-md p-1.5 text-muted-foreground opacity-60 transition-all hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
              onclick={() => clearRecent(item)}
              aria-label="Remove from list"
            >
              <Trash2 class="size-3.5" />
            </button>
          </li>
        {/each}
      </ul>
    </div>
  </Card>
{/if}
