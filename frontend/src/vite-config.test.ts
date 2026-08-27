// @vitest-environment node

import type { UserConfig } from "vite";
import { describe, expect, it } from "vitest";
import config from "../vite.config";

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
