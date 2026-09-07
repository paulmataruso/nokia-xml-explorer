import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev mode, proxy /api to the backend container/service so the same
// frontend code works both with `vite dev` and behind the production
// FastAPI static-file server (which serves the built assets itself).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.BACKEND_URL || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
