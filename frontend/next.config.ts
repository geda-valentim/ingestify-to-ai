import type { NextConfig } from "next";

// Same default as lib/api.ts: the origin the browser calls for the API.
const apiOrigin = (() => {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080").origin;
  } catch {
    return "";
  }
})();

// /admin shows engines, budgets and masked credentials (spec 0003, slice 5): a tighter
// policy there. Next's bootstrap scripts are inline (no nonce), hence 'unsafe-inline';
// 'unsafe-eval' only for the dev server's hot reload.
const adminCsp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self' ${apiOrigin}`.trim(),
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  output: 'standalone',

  async headers() {
    return [
      {
        source: "/admin/:path*",
        headers: [
          { key: "Content-Security-Policy", value: adminCsp },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },

  // Prevent canvas from being bundled on server
  serverExternalPackages: ['canvas'],

  webpack: (config) => {
    // Add fallback for canvas module
    config.resolve.fallback = {
      ...config.resolve.fallback,
      canvas: false,
    };

    return config;
  },
};

export default nextConfig;
