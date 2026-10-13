import { defineConfig, devices } from "@playwright/test";

// End-to-end tests against the real Flask API serving the built frontend.
// Weather is stubbed in the tests so they don't depend on Open-Meteo.
const PORT = Number(process.env.E2E_PORT ?? 8790);
const PYTHON = process.env.PYTHON ?? "../.venv/bin/python";

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: `npm run build && ${PYTHON} -m flask --app "snow_flights.app:create_app()" run --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    env: { PYTHONPATH: "../src", SNOW_FLIGHTS_STATIC_DIR: "dist" },
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
