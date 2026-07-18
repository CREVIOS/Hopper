<script lang="ts">
  import {
    Upload,
    Download,
    File as FileIcon,
    Folder,
    Trash2,
    ChevronRight,
    RefreshCw,
    Home as HomeIcon,
    AlertCircle,
    CornerLeftUp
  } from 'lucide-svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { toast } from 'svelte-sonner';
  import { Button, Card, Input, Label, Table } from '$lib/ui';
  import { api, ApiError } from '$lib/api/client';
  import { formatBytes, relTime } from '$lib/utils';

  // Human "modified" label from a backend mtime string; tolerant of odd formats.
  function modLabel(mtime: string): string {
    if (!mtime) return '—';
    const d = new Date(mtime);
    return Number.isNaN(+d) ? mtime : relTime(d);
  }

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
  let dragOver = $state(false);
  let uploading = $state(false);
  let downloading = $state(false);
  let recent = $state<Recent[]>([]);
  let uploadInput = $state<HTMLInputElement | null>(null);

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

  // Full absolute path for an entry in the current directory.
  function entryPath(name: string): string {
    return cwd === '/' ? `/${name}` : `${cwd}/${name}`;
  }

  async function downloadFile(explicit: string) {
    const path = explicit.trim();
    const err = pathError(path);
    if (err || !path) {
      toast.error(err ?? 'Enter a path');
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

<div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
  <!-- LEFT: file browser -->
  <Card class="h-fit overflow-hidden">
    <!-- Toolbar: breadcrumb + actions -->
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 px-4 py-2.5">
      <nav class="flex min-w-0 flex-wrap items-center gap-0.5 font-mono text-xs">
        {#each breadcrumbs as crumb, i (crumb.path)}
          {#if i > 0}
            <ChevronRight class="size-3 shrink-0 text-muted-foreground/60" />
          {/if}
          <button
            class="rounded-md px-1.5 py-0.5 transition-colors hover:bg-accent hover:text-foreground disabled:cursor-default disabled:font-semibold disabled:text-foreground"
            onclick={() => loadDir(crumb.path)}
            disabled={crumb.path === cwd}
            aria-label={i === 0 ? 'Root' : crumb.label}
          >
            {#if i === 0}
              <HomeIcon class="-mt-0.5 inline size-3.5" />
            {:else}
              {crumb.label}
            {/if}
          </button>
        {/each}
      </nav>
      <div class="flex shrink-0 items-center gap-1.5">
        <Button
          variant="outline"
          size="icon"
          class="size-8"
          onclick={() => loadDir(cwd)}
          disabled={!podRunning || listing}
          aria-label="Refresh"
          title="Refresh"
        >
          <RefreshCw class="size-3.5 {listing ? 'animate-spin' : ''}" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          class="size-8"
          onclick={() => loadDir(HOME)}
          disabled={!podRunning || listing}
          aria-label="Home"
          title="Home"
        >
          <HomeIcon class="size-3.5" />
        </Button>
        <Button size="sm" onclick={() => uploadInput?.click()} disabled={!podRunning || uploading || !!destErr}>
          <Upload class="size-3.5" /> Upload
        </Button>
      </div>
    </div>

    {#if !podRunning}
      <p class="px-5 py-14 text-center text-sm text-muted-foreground">
        Start the VM to browse its files.
      </p>
    {:else if listError}
      <div class="px-5 py-4">
        <div class="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertCircle class="mt-0.5 size-4 shrink-0" />
          <span>{listError}</span>
        </div>
      </div>
    {:else if listing && entries.length === 0}
      <p class="px-5 py-14 text-center text-sm text-muted-foreground">Loading…</p>
    {:else}
      <Table.Root>
        <Table.Header class="bg-muted/40">
          <Table.Row class="hover:bg-transparent">
            <Table.Head>Name</Table.Head>
            <Table.Head class="w-24 text-right">Size</Table.Head>
            <Table.Head class="hidden w-32 text-right sm:table-cell">Modified</Table.Head>
            <Table.Head class="w-12"><span class="sr-only">Actions</span></Table.Head>
          </Table.Row>
        </Table.Header>
        <Table.Body>
          {#if cwd !== '/'}
            <Table.Row class="cursor-pointer" onclick={navigateUp}>
              <Table.Cell colspan={4} class="py-2">
                <span class="flex items-center gap-2.5 text-muted-foreground">
                  <CornerLeftUp class="size-4" />
                  <span class="font-mono">..</span>
                  <span class="text-xs">Up one level</span>
                </span>
              </Table.Cell>
            </Table.Row>
          {/if}
          {#each entries as entry (entry.name)}
            <Table.Row
              class={entry.is_dir ? 'group cursor-pointer' : 'group'}
              onclick={() => entry.is_dir && navigate(entry.name)}
            >
              <Table.Cell class="py-2">
                <span class="flex min-w-0 items-center gap-2.5">
                  {#if entry.is_dir}
                    <Folder class="size-4 shrink-0 text-amber-500" />
                  {:else}
                    <FileIcon class="size-4 shrink-0 text-muted-foreground" />
                  {/if}
                  <span class="truncate font-mono text-sm {entry.is_dir ? 'font-medium group-hover:text-primary' : ''}">
                    {entry.name}{entry.is_dir ? '/' : ''}
                  </span>
                </span>
              </Table.Cell>
              <Table.Cell class="w-24 text-right font-mono text-xs text-muted-foreground">
                {entry.is_dir ? '—' : formatBytes(entry.size)}
              </Table.Cell>
              <Table.Cell class="hidden w-32 text-right text-xs text-muted-foreground sm:table-cell">
                {modLabel(entry.mtime)}
              </Table.Cell>
              <Table.Cell class="w-12 text-right">
                {#if !entry.is_dir}
                  <button
                    class="rounded-md p-1.5 text-muted-foreground opacity-70 transition-all hover:bg-accent hover:text-foreground group-hover:opacity-100"
                    onclick={(e) => {
                      e.stopPropagation();
                      downloadFile(entryPath(entry.name));
                    }}
                    disabled={downloading}
                    aria-label={`Download ${entry.name}`}
                    title="Download"
                  >
                    <Download class="size-3.5" />
                  </button>
                {/if}
              </Table.Cell>
            </Table.Row>
          {:else}
            <Table.Row class="hover:bg-transparent">
              <Table.Cell colspan={4} class="py-14 text-center text-xs text-muted-foreground">
                Empty directory.
              </Table.Cell>
            </Table.Row>
          {/each}
        </Table.Body>
      </Table.Root>
      <div class="border-t border-border/60 px-4 py-2 text-xs text-muted-foreground">
        Click a folder to open it. Use the download icon to pull a file to your machine.
      </div>
    {/if}
  </Card>

  <!-- RIGHT: upload sidebar -->
  <div class="space-y-4">
    <Card class="overflow-hidden">
      <div class="flex items-center gap-2.5 px-4 pb-3 pt-4">
        <span class="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Upload class="size-4" />
        </span>
        <h3 class="text-sm font-semibold">Upload files</h3>
      </div>
      <div class="space-y-3 border-t border-border/60 px-4 py-4">
        <label
          class="group flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition-all {dragOver
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
            <span class="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Spinner class="size-5" />
            </span>
            <span class="text-sm font-medium text-muted-foreground">Uploading…</span>
          {:else}
            <span class="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary transition-transform group-hover:scale-105">
              <Upload class="size-5" />
            </span>
            <span class="text-sm font-medium">Drag files here</span>
            <span class="text-xs text-muted-foreground">or click to browse</span>
          {/if}
          <input
            bind:this={uploadInput}
            type="file"
            class="hidden"
            disabled={uploading || !podRunning || !!destErr}
            onchange={handleFileInput}
          />
        </label>

        <div class="space-y-1.5">
          <Label for="dest-path" class="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Destination
          </Label>
          <Input
            id="dest-path"
            bind:value={destPath}
            placeholder="/root"
            class="h-9 font-mono text-sm {destErr ? 'border-destructive' : ''}"
            aria-invalid={!!destErr}
            aria-describedby={destErr ? 'dest-err' : undefined}
          />
          {#if destErr}
            <p id="dest-err" class="text-xs text-destructive">{destErr}</p>
          {/if}
        </div>

        <p class="flex items-start gap-1.5 text-[11px] leading-relaxed text-muted-foreground">
          <AlertCircle class="mt-0.5 size-3 shrink-0 text-warning" />
          Files inside the VM are ephemeral — wiped on terminate.
        </p>
      </div>
    </Card>

    {#if recent.length > 0}
      <Card class="overflow-hidden">
        <div class="flex items-center gap-2.5 px-4 pb-3 pt-4">
          <span class="flex size-8 items-center justify-center rounded-lg bg-success/10 text-success">
            <Upload class="size-4" />
          </span>
          <h3 class="text-sm font-semibold">Recent uploads</h3>
        </div>
        <ul class="max-h-[16rem] divide-y divide-border/60 overflow-y-auto border-t border-border/60">
          {#each recent as item (item.at.toISOString() + item.name)}
            <li class="group flex items-center gap-2.5 px-4 py-2.5 transition-colors hover:bg-muted/40">
              <span class="flex size-7 shrink-0 items-center justify-center rounded-md bg-success/10 text-success">
                <FileIcon class="size-3.5" />
              </span>
              <div class="min-w-0 flex-1">
                <div class="truncate font-mono text-xs font-medium">{item.name}</div>
                <div class="truncate text-[11px] text-muted-foreground">
                  {formatBytes(item.size)} · {relTime(item.at)}
                </div>
              </div>
              <button
                class="rounded-md p-1 text-muted-foreground opacity-0 transition-all hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                onclick={() => clearRecent(item)}
                aria-label="Remove from list"
              >
                <Trash2 class="size-3.5" />
              </button>
            </li>
          {/each}
        </ul>
      </Card>
    {/if}
  </div>
</div>
