import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // backend FastAPI dev server (CORS already allows 5173 via APP__CORS_ORIGINS)
    proxy: {},
  },
});
