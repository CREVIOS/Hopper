import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  server: {
    proxy: {
      // Auth routes — must NOT follow redirects so Keycloak redirects
      // go back to the browser (not resolved server-side by Vite)
      '/api/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        followRedirects: false,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // VS Code proxy — follow redirects and support WebSocket
      '/api/pods': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        followRedirects: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        ws: true,
      },
      // Everything else
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        followRedirects: false,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    }
  }
});
