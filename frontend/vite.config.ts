import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

const proxyErrorHandlers = (proxy: any) => {
  proxy.on('error', (err: Error, req: any, res: any) => {
    console.error('[vite proxy] error:', req.url, err.message);
    if (res && !res.headersSent) {
      try { res.writeHead(502); res.end(`Proxy error: ${err.message}`); } catch {}
    }
  });
  proxy.on('proxyReqWs', (_pr: any, req: any, socket: any) => {
    socket.on('error', (e: Error) => console.error('[vite proxy ws]', req.url, e));
  });
};

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  server: {
    proxy: {
      // Auth routes — must NOT follow redirects so Keycloak redirects
      // go back to the browser (not resolved server-side by Vite)
      '/api/auth': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        followRedirects: false,
        rewrite: (path) => path.replace(/^\/api/, ''),
        configure: proxyErrorHandlers,
      },
      // Pod routes — VS Code proxy + WebSocket terminal both go through here.
      // Follow redirects so code-server's internal redirects resolve, and
      // enable WS for both the code-server WS path and /pods/{id}/terminal.
      '/api/pods': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        followRedirects: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        ws: true,
        configure: proxyErrorHandlers,
      },
      // Everything else
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        followRedirects: false,
        rewrite: (path) => path.replace(/^\/api/, ''),
        configure: proxyErrorHandlers,
      },
    }
  }
});
