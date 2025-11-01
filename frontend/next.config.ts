import type { NextConfig } from "next";
import path from "path";
import webpack from "webpack";

const nextConfig: NextConfig = {
  output: 'standalone',

  // Prevent canvas from being bundled on server
  serverExternalPackages: ['canvas'],

  webpack: (config, { isServer }) => {
    // Completely ignore canvas module (used by pdfjs-dist for Node.js environments)
    config.plugins.push(
      new webpack.IgnorePlugin({
        resourceRegExp: /^canvas$/,
        contextRegExp: /pdfjs-dist/,
      })
    );

    // Also add fallback
    config.resolve.fallback = {
      ...config.resolve.fallback,
      canvas: false,
    };

    return config;
  },
};

export default nextConfig;
