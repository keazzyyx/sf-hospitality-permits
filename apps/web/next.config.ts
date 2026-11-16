import path from "node:path";
import type { NextConfig } from "next";

const isProd = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // `page.dev.tsx` routes (the memo fixture preview under /dev) exist only outside production builds.
  pageExtensions: isProd ? ["tsx", "ts"] : ["dev.tsx", "tsx", "ts"],
  transpilePackages: ["@sfhp/catalog"],
  poweredByHeader: false,
  // Monorepo root, so file tracing on Vercel picks up packages/catalog and the pnpm store.
  outputFileTracingRoot: path.join(__dirname, "../../"),
  images: { formats: ["image/avif", "image/webp"] },
};

export default nextConfig;
