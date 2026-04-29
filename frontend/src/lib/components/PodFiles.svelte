<script lang="ts">
  import {
    Upload,
    Download,
    File as FileIcon,
    FolderOpen,
    Loader2,
    Trash2
  } from 'lucide-svelte';
  import { toast } from 'svelte-sonner';
  import { Button, Card, CardContent, Input, Label, Separator } from '$lib/ui';
  import { api, ApiError } from '$lib/api/client';
  import { formatBytes, relTime } from '$lib/utils';

  let { podId, podRunning }: { podId: string; podRunning: boolean } = $props();

  type Recent = { name: string; size: number; dest: string; at: Date };

  let destPath = $state('/home');
  let downloadPath = $state('/home/');
  let dragOver = $state(false);
  let uploading = $state(false);
  let downloading = $state(false);
  let recent = $state<Recent[]>([]);

  async function uploadFile(file: File) {
    if (uploading) return;
    if (!podRunning) {
      toast.error('VM is not running');
      return;
    }
    uploading = true;
    const id = toast.loading(`Uploading ${file.name}…`);
    const form = new FormData();
    form.append('file', file);
    try {
      const dest = destPath.trim() || '/home';
      await api.upload(
        `/files/${podId}/upload?dest_path=${encodeURIComponent(dest)}`,
        form
      );
      recent = [
        { name: file.name, size: file.size, dest, at: new Date() },
        ...recent
      ].slice(0, 8);
      toast.success(`Uploaded ${file.name}`, { id, description: `→ ${dest}` });
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
    if (!path) {
      toast.error('Enter a path');
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
</script>

<div class="grid gap-4 lg:grid-cols-2">
  <!-- Upload -->
  <Card>
    <CardContent class="space-y-4 pt-6">
      <div>
        <h3 class="flex items-center gap-2 text-sm font-semibold">
          <Upload class="size-4 text-primary" /> Upload to VM
        </h3>
        <p class="mt-1 text-xs text-muted-foreground">
          Files are pushed via SCP using the VM's SSH credentials.
        </p>
      </div>

      <div>
        <Label for="dest-path">Destination path</Label>
        <Input
          id="dest-path"
          bind:value={destPath}
          placeholder="/home"
          class="font-mono"
        />
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
          disabled={uploading || !podRunning}
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
          Provide an absolute path inside the VM (e.g. <code class="font-mono">/home/output.txt</code>).
        </p>
      </div>
      <div>
        <Label for="dl-path">File path</Label>
        <Input
          id="dl-path"
          bind:value={downloadPath}
          placeholder="/home/output.txt"
          class="font-mono"
        />
      </div>
      <Button
        onclick={downloadFile}
        disabled={downloading || !podRunning}
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
