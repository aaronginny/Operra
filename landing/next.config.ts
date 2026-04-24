import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // GLB files live in public/ and are served as static assets — no bundler rule needed.
  // Empty turbopack config silences the "webpack config ignored" warning.
  turbopack: {},
};

export default nextConfig;
