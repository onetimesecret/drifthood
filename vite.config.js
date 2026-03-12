import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [tailwindcss(), svelte()],
  server: {
    proxy: {
      '/api': 'http://localhost:8899',
    },
  },
  build: {
    outDir: 'dist',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.js'],
  },
  // Svelte 5 exports client vs server entry points via the "browser" condition.
  // Without this, jsdom resolves to the server bundle and mount() is unavailable.
  resolve: {
    conditions: ['browser'],
  },
});
