import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig, loadEnv } from 'vite';

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

export default defineConfig(({ mode }) => {
  // Load every env var (empty prefix = include non-VITE_ vars too) so the dev
  // proxy can be pointed at a backend without editing this file.
  const env = loadEnv(mode, process.cwd(), '');

  // Where to forward /api/* during `vite dev`.
  //  - Local api-gateway (default): http://127.0.0.1:8000
  //  - A deployed environment:      https://hopper.farefin.com
  const apiTarget = env.API_PROXY_TARGET || 'http://127.0.0.1:8000';

  // The local api-gateway serves routes WITHOUT an /api prefix, so we strip it.
  // A deployed ingress strips /api itself and would 404 on the doubled path,
  // so set API_PROXY_STRIP_PREFIX=false when targeting an ingress/remote host.
  const stripApiPrefix = (env.API_PROXY_STRIP_PREFIX ?? 'true') !== 'false';
  const rewrite = stripApiPrefix
    ? (path: string) => path.replace(/^\/api/, '')
    : undefined;

  // Don't reject self-signed/staging certs when proxying to an https backend.
  const secure = (env.API_PROXY_SECURE ?? 'false') === 'true';

  const common = {
    target: apiTarget,
    changeOrigin: true,
    secure,
    rewrite,
    configure: proxyErrorHandlers,
  } as const;

  return {
    plugins: [tailwindcss(), sveltekit()],
    // Several Svelte-only packages (mode-watcher, bits-ui, svelte-sonner,
    // lucide-svelte) ship only the `svelte` export condition. SSR needs them
    // bundled rather than externalised so vite resolves through the svelte
    // plugin instead of the commonjs resolver.
    ssr: {
      noExternal: ['mode-watcher', 'bits-ui', 'svelte-sonner', 'lucide-svelte']
    },
    server: {
      proxy: {
        // Auth routes — must NOT follow redirects so Keycloak redirects
        // go back to the browser (not resolved server-side by Vite)
        '/api/auth': { ...common, followRedirects: false },
        // Pod routes — VS Code proxy + WebSocket terminal both go through here.
        // Follow redirects so code-server's internal redirects resolve, and
        // enable WS for both the code-server WS path and /pods/{id}/terminal.
        '/api/pods': { ...common, followRedirects: true, ws: true },
        // Everything else
        '/api': { ...common, followRedirects: false },
      }
    }
  };
});
