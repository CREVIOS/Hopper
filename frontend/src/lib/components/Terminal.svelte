<script lang="ts">
  import '@xterm/xterm/css/xterm.css';

  let {
    sessionId = '',
    podId = '',
    isActive = true,
    onClose,
  }: {
    sessionId: string;
    podId: string;
    isActive?: boolean;
    onClose?: () => void;
  } = $props();

  let terminalEl: HTMLDivElement;
  let connectionStatus = $state<'connecting' | 'connected' | 'reconnecting' | 'closed'>('connecting');
  let statusMessage = $state('Connecting to pod…');

  // Shared so the activation effect can drive focus()/fit() when this tab
  // becomes visible. xterm's FitAddon returns garbage when the element is
  // hidden (parent width computes to "auto"); we must refit on activation.
  let termRef: any = null;
  let fitAddonRef: any = null;
  let wsRef: WebSocket | null = null;

  // Refocus + refit when this terminal becomes the active tab. Without this,
  // a "+"-spawned new tab leaves DOM focus on the previous xterm so keystrokes
  // go to the wrong terminal, and a backgrounded tab keeps stale rows/cols
  // from the moment its parent had clientHeight === 0 / opacity-0.
  $effect(() => {
    if (!isActive || !termRef) return;
    queueMicrotask(() => {
      try { termRef.focus(); } catch {}
      try {
        if (fitAddonRef && terminalEl && terminalEl.clientHeight > 0) {
          fitAddonRef.fit();
          if (
            wsRef && wsRef.readyState === WebSocket.OPEN
            && termRef.cols > 0 && termRef.rows > 0
          ) {
            wsRef.send(JSON.stringify({ type: 'resize', cols: termRef.cols, rows: termRef.rows }));
          }
        }
      } catch {}
    });
  });

  // Single $effect handles full lifecycle (setup + teardown) — runes-native,
  // avoids the chunk-split runtime-context mismatch that broke onMount/onDestroy.
  $effect(() => {
    let term: any;
    let ws: WebSocket | null = null;
    let fitAddon: any;
    let resizeObserver: ResizeObserver | null = null;
    let reconnectTimer: number | undefined;
    let resizeTimer: number | undefined;
    let heartbeatTimer: number | undefined;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    let cancelled = false;

    function connect() {
      if (cancelled) return;

      connectionStatus = reconnectAttempts > 0 ? 'reconnecting' : 'connecting';
      statusMessage =
        reconnectAttempts > 0
          ? `Reconnecting to terminal (attempt ${reconnectAttempts + 1}/${maxReconnectAttempts})…`
          : 'Connecting to pod…';

      if (term) term.writeln('\r\nConnecting to pod...');

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${protocol}//${window.location.host}/api/pods/${podId}/terminal`);
      wsRef = ws;

      ws.onopen = () => {
        if (cancelled) return;
        reconnectAttempts = 0;
        connectionStatus = 'connected';
        statusMessage = 'Connected';
        if (term) {
          term.writeln('\r\nConnected!\r\n');
          try { term.focus(); } catch {}
        }
        if (fitAddon && terminalEl && terminalEl.clientHeight > 0) {
          try {
            fitAddon.fit();
            if (term.cols > 0 && term.rows > 0) {
              ws?.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
            }
          } catch {}
        }
        // App-level heartbeat — keeps idle proxies (LB / nginx) from dropping
        // the connection. The api-gateway recognises and discards these.
        clearInterval(heartbeatTimer);
        heartbeatTimer = window.setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            try { ws.send('{"type":"ping"}'); } catch {}
          }
        }, 20000);
      };

      ws.onmessage = (ev) => {
        if (cancelled || !term) return;
        try {
          term.write(ev.data);
        } catch (e) {
          console.error('Terminal write error:', e);
        }
      };

      ws.onerror = (ev) => {
        console.error('WebSocket error:', ev);
      };

      ws.onclose = (ev) => {
        clearInterval(heartbeatTimer);
        if (cancelled) return;

        const code = ev.code;
        if (code === 1008 || code === 1003 || code >= 4000) {
          connectionStatus = 'closed';
          statusMessage = `Connection closed (${code})`;
          if (term) term.writeln(`\r\nConnection closed (${code}).`);
          return;
        }

        if (reconnectAttempts >= maxReconnectAttempts) {
          connectionStatus = 'closed';
          statusMessage = 'Max reconnect attempts reached. Please refresh.';
          if (term) term.writeln(`\r\nMax reconnect attempts reached. Please refresh.`);
          return;
        }

        const backoff = Math.min(3000 * Math.pow(1.5, reconnectAttempts), 15000);
        reconnectAttempts++;
        connectionStatus = 'reconnecting';
        statusMessage = `Disconnected. Reconnecting in ${Math.round(backoff / 1000)}s…`;

        if (term) {
          term.writeln(`\r\nConnection lost — Reconnecting in ${Math.round(backoff / 1000)}s (Attempt ${reconnectAttempts}/${maxReconnectAttempts})...`);
        }
        clearTimeout(reconnectTimer);
        reconnectTimer = window.setTimeout(connect, backoff);
      };
    }

    (async () => {
      const { Terminal } = await import('@xterm/xterm');
      const { FitAddon } = await import('@xterm/addon-fit');
      const { WebLinksAddon } = await import('@xterm/addon-web-links');

      if (cancelled || !terminalEl) return;

      term = new Terminal({ cursorBlink: true, fontSize: 14, fontFamily: 'monospace' });
      fitAddon = new FitAddon();

      term.loadAddon(fitAddon);
      term.loadAddon(new WebLinksAddon());
      term.open(terminalEl);
      // Expose to the activation effect.
      termRef = term;
      fitAddonRef = fitAddon;

      term.onData((data: string) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(data);
        }
      });

      term.onResize((size: { cols: number; rows: number }) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'resize', cols: size.cols, rows: size.rows }));
        }
      });

      resizeObserver = new ResizeObserver(() => {
        if (fitAddon && terminalEl && terminalEl.clientHeight > 0) {
          try { fitAddon.fit(); } catch {}
        }
      });

      // Defer observation slightly so the container has its final size.
      resizeTimer = window.setTimeout(() => {
        if (!cancelled && terminalEl && resizeObserver) resizeObserver.observe(terminalEl);
      }, 100);

      connect();
    })();

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      clearTimeout(resizeTimer);
      clearInterval(heartbeatTimer);
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        ws.close();
      }
      if (resizeObserver) resizeObserver.disconnect();
      if (term) term.dispose();
    };
  });
</script>

<div class="relative h-full w-full bg-black rounded border border-gray-800">
  <div
    class="absolute left-3 top-2 z-10 rounded bg-gray-900/85 px-2 py-1 text-xs text-gray-200"
    role="status"
    aria-live="polite"
    data-terminal-status={connectionStatus}
  >
    {statusMessage}
  </div>
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
