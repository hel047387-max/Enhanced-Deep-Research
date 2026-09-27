import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { VitePWA, type VitePWAOptions } from "vite-plugin-pwa";

export const pwaOptions: Partial<VitePWAOptions> = {
  strategies: "generateSW",
  registerType: "autoUpdate",
  manifest: {
    name: "Deep Research Workspace",
    short_name: "Deep Research",
    description: "Private evidence-grounded research workspace",
    start_url: "/",
    scope: "/",
    display: "standalone",
    theme_color: "#173d31",
    background_color: "#edf0e7",
    icons: [
      { src: "/pwa-192x192.png", sizes: "192x192", type: "image/png" },
      { src: "/pwa-512x512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/maskable-icon-512x512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  },
  workbox: {
    globPatterns: ["**/*.{js,css,html,png,svg,ico,woff2}"],
    globIgnores: [
      "pwa-192x192.png",
      "pwa-512x512.png",
      "maskable-icon-512x512.png",
    ],
    navigateFallback: null,
    runtimeCaching: [
      {
        urlPattern: ({ request, url }) =>
          request.mode === "navigate" &&
          url.pathname !== "/api" &&
          !url.pathname.startsWith("/api/") &&
          url.pathname !== "/health",
        handler: "NetworkOnly",
        options: {
          precacheFallback: {
            fallbackURL: "/offline.html",
          },
        },
      },
    ],
  },
};

export default defineConfig({
  plugins: [vue(), VitePWA(pwaOptions)],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
