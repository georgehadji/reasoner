import type { NextConfig } from "next";
import path from "path";
import { buildContentSecurityPolicy } from "./src/lib/security-csp";

let withBundleAnalyzer = (config: NextConfig) => config;
try {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  withBundleAnalyzer = require("@next/bundle-analyzer")({ enabled: process.env.ANALYZE === "true" });
} catch {
  // @next/bundle-analyzer is optional; skip if not installed
}

const HSTS_VALUE = 'max-age=31536000; includeSubDomains; preload';

const nextConfig: NextConfig = {
  output: 'standalone',
  transpilePackages: ['three', '@react-three/fiber', '@react-three/drei', '@react-three/postprocessing', 'postprocessing'],
  turbopack: {
    root: path.resolve(__dirname),
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Content-Security-Policy', value: buildContentSecurityPolicy() },
          ...(process.env.NODE_ENV === 'production'
            ? [{ key: 'Strict-Transport-Security', value: HSTS_VALUE }]
            : []),
        ],
      },
    ];
  },
};

export default withBundleAnalyzer(nextConfig);
