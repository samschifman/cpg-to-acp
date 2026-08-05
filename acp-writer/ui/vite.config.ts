import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@app": resolve(__dirname, "src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8082",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8082",
        changeOrigin: true,
      },
    },
  },
});
