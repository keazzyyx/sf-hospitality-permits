import { homedir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

// The public site's build, served as Vercel serves it (tools/serve-site.mjs: vercel.json's headers, the CSP), held
// to the live site as it was before the C front end (the same folder served the same way). Local only: both
// folders are outside the repository. A missing folder skips the tests.
//
//   python3 scripts/validation/build_public_conditions_site.py --front c --out <dir> --manifest <file>
//   SITE_DIR=<dir> pnpm --filter showcase test:site
//
// SITE_DIR      the build to test (default: the builder's own output, $LOCAL_DATA_DIR/sf-conditions-search-site;
//               LOCAL_DATA_DIR defaults to ~/sfhp-local, as for the builder)
// BASELINE_DIR  the site to compare it with (default: the live site's folder as it was before C,
//               $LOCAL_DATA_DIR/sf-conditions-search-site.pre-c-2026-11-17)
// SITE_PORT     where the build is served (default 4413); BASELINE_PORT the baseline (default SITE_PORT - 1)

const here = dirname(fileURLToPath(import.meta.url));
const localDataDir = process.env.LOCAL_DATA_DIR?.trim() || "~/sfhp-local";
const local = localDataDir.startsWith("~/") ? resolve(homedir(), localDataDir.slice(2)) : resolve(localDataDir);
export const SITE_DIR = resolve(process.env.SITE_DIR ?? resolve(local, "sf-conditions-search-site"));
export const BASELINE_DIR = resolve(process.env.BASELINE_DIR ?? resolve(local, "sf-conditions-search-site.pre-c-2026-11-17"));
const sitePort = Number(process.env.SITE_PORT ?? 4413);
const baselinePort = Number(process.env.BASELINE_PORT ?? sitePort - 1);
export const SITE = `http://127.0.0.1:${sitePort}`;
export const BASELINE = `http://127.0.0.1:${baselinePort}`;

const serve = (dir: string, port: number) => ({
  command: `node tools/serve-site.mjs ${JSON.stringify(dir)} ${port}`,
  url: `http://127.0.0.1:${port}/__views`,
  cwd: here,
  reuseExistingServer: false,
  timeout: 30_000,
});

export default defineConfig({
  testDir: "./e2e-site",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: "list",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  use: { baseURL: SITE, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [serve(SITE_DIR, sitePort), serve(BASELINE_DIR, baselinePort)],
});
