import type { NextConfig } from "next";

const apiUrl = (process.env.API_URL || "http://127.0.0.1:8001").replace(
  /\/$/,
  "",
);
const config: NextConfig = {
  experimental: { proxyTimeout: 300_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};
export default config;
