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

  it("uses the offline page only when a navigation request fails", () => {
    expect(pwaOptions.workbox?.navigateFallback).toBeNull();
    const rules = pwaOptions.workbox?.runtimeCaching ?? [];
    expect(rules).toHaveLength(1);
    expect(rules[0]).toMatchObject({
      handler: "NetworkOnly",
      options: { precacheFallback: { fallbackURL: "/offline.html" } },
    });
    const matches = rules[0].urlPattern as (context: {
      request: { mode: string };
      url: URL;
    }) => boolean;
    const context = (pathname: string, mode = "navigate") => ({
      request: { mode },
      url: new URL(pathname, "https://research.example"),
    });
    expect(matches(context("/research"))).toBe(true);
    expect(matches(context("/research", "cors"))).toBe(false);
    expect(matches(context("/api"))).toBe(false);
    expect(matches(context("/api/v1/auth/status"))).toBe(false);
    expect(matches(context("/health"))).toBe(false);
  });
});
