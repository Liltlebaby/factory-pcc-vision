import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produce a minimal self-contained Node server for the production image.
  output: "standalone",
  // Allow development assets/HMR from this PC and its current factory LAN IP.
  allowedDevOrigins: ["127.0.0.1", "192.168.1.50"],
};

export default nextConfig;
