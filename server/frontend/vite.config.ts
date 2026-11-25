import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { federationOffline } from "./offline/vite-offline.mjs";

export default defineConfig({
  plugins: [react(), federationOffline({ appId: "spiderweb-pr" })],
  server: {
    port: 5173,
    proxy: {
      "/tiles": {
        target: "http://127.0.0.1:3000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/tiles/, ""),
      },
    },
  },
});
