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
      window.reconnectAttempts = 0;
      if (term) {
         term.writeln('\r\nConnected!\r\n');
         try { term.focus(); } catch (e) {}
      }
      if (fitAddon && terminalEl && terminalEl.clientHeight > 0) {
         try {
           fitAddon.fit();
           if (term.cols > 0 && term.rows > 0) {
             ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
           }
         } catch (e) {}
      }
    };

    ws.onmessage = (ev) => {
        if (isDisposed || !term) return;
        try {
          term.write(ev.data);
        } catch (e) {
          console.error("Terminal write error:", e);
        }
    };

    ws.onerror = (ev) => {
      console.error("WebSocket error:", ev);
    };

    ws.onclose = (ev) => {
      if (isDisposed) return;

      const code = ev.code;
      if (code === 1008 || code === 1003 || code >= 4000) {
        term.writeln(`\r\nConnection closed (${code}).`);
        return;
      }

      if (typeof reconnectAttempts === 'undefined' || typeof maxReconnectAttempts === 'undefined') {
         window.reconnectAttempts = (window.reconnectAttempts || 0);
         window.maxReconnectAttempts = 5;
      }

      if (window.reconnectAttempts >= window.maxReconnectAttempts) {
        term.writeln(`\r\nMax reconnect attempts reached. Please refresh.`);
        return;
      }

      const backoff = Math.min(3000 * Math.pow(1.5, window.reconnectAttempts), 15000);
      window.reconnectAttempts++;

      term.writeln(`\r\nConnection lost — Reconnecting in ${Math.round(backoff / 1000)}s (Attempt ${window.reconnectAttempts}/${window.maxReconnectAttempts})...`);
      clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(connect, backoff);
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
       if (fitAddon && terminalEl && terminalEl.clientHeight > 0) {
          try {
             fitAddon.fit();
          } catch (e) {}
       }
    });

    // Wait for the terminal container to be fully rendered before observing
    resizeTimer = window.setTimeout(() => {
        if (!isDisposed && terminalEl) resizeObserver.observe(terminalEl);
    }, 100);

    connect();
  });

  onDestroy(() => {
    isDisposed = true;
    clearTimeout(reconnectTimer);
    clearTimeout(resizeTimer);
    if (ws) {
        ws.onclose = null;
        ws.close();
    }
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
