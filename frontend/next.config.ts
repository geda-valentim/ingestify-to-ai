import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone',

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
