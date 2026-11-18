import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const here = dirname(fileURLToPath(import.meta.url));

// Several builders run the suite in this tree at once: SHOWCASE_PORT (dev; preview is the next port up),
// SHOWCASE_CURRENT_PORT and SHOWCASE_OUT (the build folder, read by vite.config.ts) keep them apart.
const devPort = Number(process.env.SHOWCASE_PORT ?? 4310);
const previewPort = devPort + 1;
const currentPort = Number(process.env.SHOWCASE_CURRENT_PORT ?? devPort + 2);

/** The built showcase (vite preview). */
export const SHOWCASE = `http://127.0.0.1:${previewPort}`;
/** The current site, served unchanged from tools/conditions-search: what the parity tests compare against. */
export const CURRENT = `http://127.0.0.1:${currentPort}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  // (on a CI runner a test that holds a key for a set time can lose to a busy machine: one more try there)
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: SHOWCASE,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // a CI runner has no graphics card: the tests that force the 3D scene (?webgl=1) need WebGL drawn in software
        launchOptions: process.env.CI ? { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] } : {},
      },
    },
  ],
  webServer: [
    {
      command: `pnpm exec vite build && pnpm exec vite preview --port ${previewPort} --strictPort --host 127.0.0.1`,
      url: `${SHOWCASE}/search/`,
      cwd: here,
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: `python3 -m http.server ${currentPort} --bind 127.0.0.1 --directory ${JSON.stringify(resolve(here, "../../tools/conditions-search"))}`,
      url: `${CURRENT}/index.html`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
