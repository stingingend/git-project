import type { NextConfig } from "next";

const apiUrl = (
  process.env.API_INTERNAL_HOSTPORT
    ? `http://${process.env.API_INTERNAL_HOSTPORT}`
    : process.env.API_URL || "http://127.0.0.1:8001"
).replace(/\/$/, "");
const config: NextConfig = {
  output: process.env.DOCKER_BUILD === "1" ? "standalone" : undefined,
  experimental: { proxyTimeout: 300_000 },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};
export default config;
