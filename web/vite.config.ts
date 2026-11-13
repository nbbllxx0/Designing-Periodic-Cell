import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The amm GUI backend (python -m app.server --mock) listens on 127.0.0.1:8766 (AMM_GUI_PORT).
const backend = `http://127.0.0.1:${process.env.AMM_GUI_PORT ?? "8766"}`;

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: Number(process.env.AMM_WEB_PORT ?? 5174),
    strictPort: true,
    proxy: { "/api": { target: backend, changeOrigin: false } },
  },
});
