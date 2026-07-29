import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    // A packaged runtime must never retain unreferenced bundles from an older
    // product build, even when developers reuse a local ignored dist folder.
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/health': 'http://127.0.0.1:8000',
      '/sites': 'http://127.0.0.1:8000',
      '/events': 'http://127.0.0.1:8000',
      '/anomalies': 'http://127.0.0.1:8000',
      '/sources': 'http://127.0.0.1:8000',
      '/catalog': 'http://127.0.0.1:8000',
      '/geo': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
