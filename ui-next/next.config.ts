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
  turbopack: {
    root: path.resolve(__dirname),
  },

  // Order is a preference list, not a fallback list: the optimizer serves the
  // first entry the request's Accept header allows. AVIF ahead of WebP is worth
  // roughly another 20% off an already-optimized WebP, and every browser that
  // lacks AVIF still gets WebP rather than the original PNG/JPEG.
  images: {
    formats: ['image/avif', 'image/webp'],
  },

  // Both are Next defaults; pinned explicitly so a future edit has to be
  // deliberate about regressing them.
  //
  // `compress` gzips responses from the standalone Node server. Leave it on
  // even behind a CDN or nginx — it is the floor when nothing else terminates.
  compress: true,

  // Client source maps stay off in production: they roughly double what the
  // browser can be asked to download and publish readable app source. Server
  // stack traces are unaffected.
  productionBrowserSourceMaps: false,
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
