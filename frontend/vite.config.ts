import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The Flask API from `make dev` / `make dev-api` (port 8010 unless API_PORT is set).
    proxy: { "/api": `http://localhost:${process.env.API_PORT ?? "8010"}` },
  },
  build: {
    outDir: "dist",
    assetsInlineLimit: 0,
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
  },
});
