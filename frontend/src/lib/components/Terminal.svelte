<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import '@xterm/xterm/css/xterm.css';

  let { sessionId = '', podId = '', onClose }: { sessionId: string, podId: string, onClose?: () => void } = $props();

  let terminalEl: HTMLDivElement;
  let term: any;
  let ws: WebSocket;
  let fitAddon: any;
  let resizeObserver: ResizeObserver;
  let isDisposed = false;
  let reconnectTimer: number;

  function connect() {
    if (isDisposed) return;
    
    if (term) term.writeln('\r\nConnecting to pod...');
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/api/pods/${podId}/terminal`);

    ws.onopen = () => {
      if (isDisposed) return;
      term.writeln('\r\nConnected!\r\n');
      term.focus();
      if (fitAddon) {
        fitAddon.fit();
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
      }
    };

    ws.onmessage = async (ev) => {
        if (isDisposed) return;
        term.write(ev.data);
    };

    ws.onclose = () => {
      if (!isDisposed) {
        term.writeln('\r\nConnection lost — Reconnecting...');
        clearTimeout(reconnectTimer);
        reconnectTimer = window.setTimeout(connect, 3000);
      }
    };
  }

  onMount(async () => {
    const { Terminal } = await import('@xterm/xterm');
    const { FitAddon } = await import('@xterm/addon-fit');
    const { WebLinksAddon } = await import('@xterm/addon-web-links');

    term = new Terminal({ cursorBlink: true, fontSize: 14, fontFamily: 'monospace' });
    fitAddon = new FitAddon();

    term.loadAddon(fitAddon);
    term.loadAddon(new WebLinksAddon());
    term.open(terminalEl);
    
    term.onData((data: string) => {
       if (ws && ws.readyState === WebSocket.OPEN) {
         ws.send(data);
       }
    });

    term.onResize((size: {cols: number, rows: number}) => {
       if (ws && ws.readyState === WebSocket.OPEN) {
         ws.send(JSON.stringify({ type: 'resize', cols: size.cols, rows: size.rows }));
       }
    });

    resizeObserver = new ResizeObserver(() => {
       if (fitAddon) {
          fitAddon.fit();
       }
    });
    // Wait for the terminal container to be fully rendered before observing
    setTimeout(() => resizeObserver.observe(terminalEl), 100);

    connect();
  });

  onDestroy(() => {
    isDisposed = true;
    clearTimeout(reconnectTimer);
    if (ws) ws.close();
    if (resizeObserver) resizeObserver.disconnect();
    if (term) term.dispose();
  });
</script>

<div class="relative h-full w-full bg-black rounded border border-gray-800">
  {#if onClose}
    <button
      title="Close Terminal"
      class="absolute top-2 right-4 z-10 p-1 text-gray-400 hover:text-white hover:bg-gray-700 bg-gray-900/80 rounded"
      onclick={onClose}
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
    </button>
  {/if}
  <div bind:this={terminalEl} class="h-full w-full p-2"></div>
</div>
