import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        configure: (proxy) => {
          proxy.on('error', (err, req, res) => {
            console.error('[vite proxy] error:', req.url, err.message);
            if (res && !res.headersSent) {
              try { res.writeHead(502); res.end(`Proxy error: ${err.message}`); } catch {}
            }
          });
          proxy.on('proxyReqWs', (_pr, req, socket) => {
            socket.on('error', (e) => console.error('[vite proxy ws]', req.url, e));
          });
        }
      }
    }
  }
});
