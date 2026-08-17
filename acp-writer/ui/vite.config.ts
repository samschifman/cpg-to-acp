import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Force a single copy of these so the file: shared/ui package and the app
    // share one react-router-dom instance — otherwise AppShell's useLocation()
    // binds to a different Router context than the app's <BrowserRouter> and
    // the app crashes with "useLocation() may be used only in the context of a
    // <Router> component."
    dedupe: ["react", "react-dom", "react-router-dom"],
    alias: {
      "@app": resolve(__dirname, "src"),
    },
  },
  server: {
    port: 3001,
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
