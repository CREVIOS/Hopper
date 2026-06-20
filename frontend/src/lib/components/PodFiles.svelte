<script lang="ts">
  import {
    Upload,
    Download,
    File as FileIcon,
    Folder,
    FolderOpen,
    Loader2,
    Trash2,
    ChevronRight,
    RefreshCw,
    Home as HomeIcon
  } from 'lucide-svelte';
  import { toast } from 'svelte-sonner';
  import { Button, Card, CardContent, Input, Label, Separator } from '$lib/ui';
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
<Card class="mb-4">
  <CardContent class="space-y-3 pt-6">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="flex items-center gap-2 text-sm font-semibold">
        <FolderOpen class="size-4 text-primary" /> VM file browser
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

    <!-- Breadcrumb -->
    <nav
      class="flex flex-wrap items-center gap-0.5 rounded-md border border-border bg-muted/30 px-2 py-1.5 font-mono text-xs"
    >
      {#each breadcrumbs as crumb, i (crumb.path)}
        {#if i > 0}
          <ChevronRight class="size-3 text-muted-foreground" />
        {/if}
        <button
          class="rounded px-1 py-0.5 hover:bg-accent disabled:cursor-default"
          onclick={() => loadDir(crumb.path)}
          disabled={crumb.path === cwd}
        >
          {crumb.label}
        </button>
      {/each}
    </nav>

    {#if !podRunning}
      <p class="py-6 text-center text-sm text-muted-foreground">
        Start the VM to browse its files.
      </p>
    {:else if listError}
      <div
        class="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
      >
        {listError}
      </div>
    {:else if listing && entries.length === 0}
      <div class="py-6 text-center text-sm text-muted-foreground">Loading…</div>
    {:else}
      <ul class="divide-y divide-border rounded-md border border-border">
        {#if cwd !== '/'}
          <li>
            <button
              class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent"
              onclick={navigateUp}
            >
              <ChevronRight class="size-4 -rotate-90 text-muted-foreground" />
              <span class="font-mono">..</span>
              <span class="text-xs text-muted-foreground">Up one level</span>
            </button>
          </li>
        {/if}
        {#each entries as entry (entry.name)}
          <li class="flex items-center gap-2 px-3 py-1.5">
            <button
              class="flex flex-1 items-center gap-2 text-left text-sm hover:text-primary"
              onclick={() => (entry.is_dir ? navigate(entry.name) : pickForDownload(entry))}
              title={entry.is_dir ? `Open ${entry.name}` : `Select ${entry.name} for download`}
            >
              {#if entry.is_dir}
                <Folder class="size-4 text-primary" />
              {:else}
                <FileIcon class="size-4 text-muted-foreground" />
              {/if}
              <span class="truncate font-mono">{entry.name}</span>
              {#if entry.is_dir}
                <span class="text-xs text-muted-foreground">/</span>
              {/if}
            </button>
            <span class="hidden text-right font-mono text-xs text-muted-foreground sm:inline">
              {entry.is_dir ? '' : formatBytes(entry.size)}
            </span>
          </li>
        {:else}
          <li class="px-3 py-6 text-center text-xs text-muted-foreground">
            Empty directory.
          </li>
        {/each}
      </ul>
      <p class="text-xs text-muted-foreground">
        Click a folder to open it, a file to select it for download. Uploads go to the
        current path.
      </p>
    {/if}
  </CardContent>
</Card>

<div class="grid gap-4 lg:grid-cols-2">
  <!-- Upload -->
  <Card>
    <CardContent class="space-y-4 pt-6">
      <div>
        <h3 class="flex items-center gap-2 text-sm font-semibold">
          <Upload class="size-4 text-primary" /> Upload to VM
        </h3>
        <p class="mt-1 text-xs text-muted-foreground">
          Files are pushed via SCP using the VM's SSH credentials. Uploads default
          to <code class="rounded bg-muted px-1 py-0.5 font-mono">/root</code> (the
          SSH home directory), or pick another directory with the browser above.
          <span class="font-medium text-foreground">
            All paths inside the VM are ephemeral in this build — they're wiped
            when the VM terminates.
          </span>
          Persistent <code class="rounded bg-muted px-1 py-0.5 font-mono">/workspace</code>
          across sessions is on the roadmap (SRS FR-HC-28).
        </p>
      </div>

      <div>
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
          <p id="dest-err" class="mt-1 text-xs text-destructive">{destErr}</p>
        {:else}
          <p class="mt-1 text-xs text-muted-foreground">
            Existing directory inside the VM, e.g. <code class="font-mono">/root</code>
            or <code class="font-mono">/workspace</code>.
          </p>
        {/if}
      </div>

      <label
        class="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors {dragOver
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
          <Loader2 class="size-6 animate-spin text-primary" />
          <span class="text-sm text-muted-foreground">Uploading…</span>
        {:else}
          <FolderOpen class="size-6 text-muted-foreground" />
          <span class="text-sm font-medium">Drop a file or click to browse</span>
          <span class="text-xs text-muted-foreground">
            Single file uploads. Max upload size depends on your gateway config.
          </span>
        {/if}
        <input
          type="file"
          class="hidden"
          disabled={uploading || !podRunning || !!destErr}
          onchange={handleFileInput}
        />
      </label>
    </CardContent>
  </Card>

  <!-- Download -->
  <Card>
    <CardContent class="space-y-4 pt-6">
      <div>
        <h3 class="flex items-center gap-2 text-sm font-semibold">
          <Download class="size-4 text-primary" /> Download from VM
        </h3>
        <p class="mt-1 text-xs text-muted-foreground">
          Click a file in the browser above to pre-fill the path, or paste an absolute
          path (e.g. <code class="font-mono">/root/output.txt</code>).
        </p>
      </div>
      <div>
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
          <p id="dl-err" class="mt-1 text-xs text-destructive">{dlErr}</p>
        {/if}
      </div>
      <Button
        onclick={downloadFile}
        disabled={downloading || !podRunning || !downloadPath || !!dlErr}
        class="w-full"
      >
        {#if downloading}
          <Loader2 class="size-4 animate-spin" /> Downloading…
        {:else}
          <Download class="size-4" /> Download
        {/if}
      </Button>
    </CardContent>
  </Card>
</div>

{#if recent.length > 0}
  <Card class="mt-4">
    <CardContent class="pt-6">
      <h3 class="mb-3 text-sm font-semibold">Recent uploads (this session)</h3>
      <Separator />
      <ul class="divide-y divide-border">
        {#each recent as item (item.at.toISOString() + item.name)}
          <li class="flex items-center gap-3 py-3">
            <FileIcon class="size-4 text-muted-foreground" />
            <div class="min-w-0 flex-1">
              <div class="truncate font-mono text-sm">{item.name}</div>
              <div class="text-xs text-muted-foreground">
                {formatBytes(item.size)} · {item.dest} · {relTime(item.at)}
              </div>
            </div>
            <button
              class="rounded-md p-1 text-muted-foreground hover:bg-accent"
              onclick={() => clearRecent(item)}
              aria-label="Remove from list"
            >
              <Trash2 class="size-3.5" />
            </button>
          </li>
        {/each}
      </ul>
    </CardContent>
  </Card>
{/if}
