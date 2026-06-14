import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { viteSingleFile } from 'vite-plugin-singlefile';

// Vite configuration for the PRIIS frontend. This config enables React support
// and sets a default development port.
// VITE_OFFLINE=1 produces a single self-contained index.html (data baked in) that
// opens directly via file:// — see `npm run build:export`.
const offline = process.env.VITE_OFFLINE === '1';

export default defineConfig({
  base: offline ? './' : '/',
  plugins: [react(), ...(offline ? [viteSingleFile()] : [])],
  build: offline ? { outDir: 'export-standalone' } : {},
  server: {
    port: 5173,
  },
});