// @vitest-environment node

import type { UserConfig } from "vite";
import { describe, expect, it } from "vitest";
import config, { pwaOptions } from "../vite.config";

function resolveConfig(): UserConfig {
  return config as UserConfig;
}

describe("Vite development server", () => {
  it("proxies same-origin API requests to the local FastAPI server", () => {
    expect(resolveConfig().server?.proxy?.["/api"]).toMatchObject({
      target: "http://127.0.0.1:8000",
      changeOrigin: true,
    });
  });
});

describe("PWA configuration", () => {
  it("defines an installable standalone manifest with required icons", () => {
    expect(pwaOptions.manifest).toMatchObject({
      start_url: "/",
      scope: "/",
      display: "standalone",
    });
    if (!pwaOptions.manifest) throw new Error("PWA manifest is required.");
    expect(pwaOptions.manifest.icons).toEqual(expect.arrayContaining([
      expect.objectContaining({ src: "/pwa-192x192.png", sizes: "192x192" }),
      expect.objectContaining({ src: "/pwa-512x512.png", sizes: "512x512" }),
      expect.objectContaining({ src: "/maskable-icon-512x512.png", purpose: "maskable" }),
    ]));
  });

  it("keeps API and health requests out of runtime caching", () => {
    expect(pwaOptions.workbox).toMatchObject({
      navigateFallback: "/offline.html",
      runtimeCaching: [],
    });
    const denylist = pwaOptions.workbox?.navigateFallbackDenylist ?? [];
    expect(denylist.some((pattern) => pattern.test("/api/v1/research/stream"))).toBe(true);
    expect(denylist.some((pattern) => pattern.test("/health"))).toBe(true);
  });
});