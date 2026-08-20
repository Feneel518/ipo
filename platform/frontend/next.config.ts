import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Vercel's Next.js adapter conflicts with standalone output in Next.js 16.3.
  // Keep standalone builds for the Docker image, but let Vercel package the app.
  output: process.env.VERCEL ? undefined : "standalone",
  poweredByHeader: false,
  experimental: { optimizePackageImports: [] },
};

export default nextConfig;
