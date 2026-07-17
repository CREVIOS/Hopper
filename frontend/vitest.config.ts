import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  test: {
    environment: 'node',
    include: ['src/**/*.{test,spec}.{ts,js}'],
    coverage: {
      provider: 'v8',
      reportsDirectory: '../coverage/frontend',
      reporter: ['text', 'json-summary', 'lcov'],
      include: ['src/lib/**/*.ts', 'src/routes/**/*.ts'],
      exclude: [
        'src/**/*.test.ts',
        'src/**/*.spec.ts',
        'src/**/*.d.ts',
        'src/lib/ui/**',
        'src/app.*'
      ]
    }
  }
});
