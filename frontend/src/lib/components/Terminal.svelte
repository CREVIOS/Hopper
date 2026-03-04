<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  let { sessionId = '' }: { sessionId: string } = $props();

  let terminalEl: HTMLDivElement;
  let terminal: unknown;

  onMount(async () => {
    const { Terminal } = await import('@xterm/xterm');
    const { FitAddon } = await import('@xterm/addon-fit');
    const { WebLinksAddon } = await import('@xterm/addon-web-links');

    const term = new Terminal({ cursorBlink: true, fontSize: 14 });
    const fitAddon = new FitAddon();

    term.loadAddon(fitAddon);
    term.loadAddon(new WebLinksAddon());
    term.open(terminalEl);
    fitAddon.fit();

    term.writeln('Connecting to pod...');
    terminal = term;

    // TODO: Connect WebSocket to Teleport proxy
  });

  onDestroy(() => {
    if (terminal && typeof (terminal as { dispose: () => void }).dispose === 'function') {
      (terminal as { dispose: () => void }).dispose();
    }
  });
</script>

<div bind:this={terminalEl} class="h-96 w-full rounded border bg-black"></div>
