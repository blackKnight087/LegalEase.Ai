/** @type {import('next').NextConfig} */
const tunnelOrigin =
  process.env.NEXT_PUBLIC_TUNNEL_HOST ||
  process.env.PUBLIC_APP_URL?.replace(/^https?:\/\//, "") ||
  "";

const allowedDevOrigins = ["localhost", "127.0.0.1"];
if (tunnelOrigin) {
  allowedDevOrigins.push(tunnelOrigin);
}
if (!allowedDevOrigins.includes("*.trycloudflare.com")) {
  allowedDevOrigins.push("*.trycloudflare.com");
}

const nextConfig = {
  reactStrictMode: true,
  // Allow Cloudflare quick tunnel host in `next dev` (fixes broken client JS on trycloudflare.com).
  allowedDevOrigins,
  // Long-running chat / scan requests — avoid dev-proxy socket hang up.
  experimental: {
    proxyTimeout: 180_000,
  },
  async redirects() {
    return [
      { source: "/study", destination: "/litigation", permanent: true },
      { source: "/study/:path*", destination: "/litigation", permanent: true },
      { source: "/court-day", destination: "/litigation", permanent: true },
      {
        source: "/matters/evidence-desk",
        destination: "/litigation?tab=evidence",
        permanent: true,
      },
    ];
  },
  // Proxy API through Next.js (same origin) — avoids CORS / 127.0.0.1 vs localhost issues on Windows.
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    return [
      { source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` },
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
    ];
  },
  // App does not use next/image; disable optimizer API to reduce attack surface when self-hosted.
  images: {
    unoptimized: true,
  },
  // Production: do not leak X-Powered-By header
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(self), geolocation=()" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
