import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import ResearchHistory from "./ResearchHistory.vue";

afterEach(() => vi.unstubAllGlobals());

it("loads archived research and opens its report, limitations, and evidence", async () => {
  const fetchMock = vi.fn((url: string) => {
    const body = url.includes("/researches?")
      ? { items: [{ thread_id: "thread-1", question: "Battery study", completed_at: "2026-01-01T00:00:00Z" }] }
      : {
          thread_id: "thread-1",
          question: "Battery study",
          completed_at: "2026-01-01T00:00:00Z",
          report: "# Archived report",
          draft: { limitations: ["One source"] },
          evidence: [{ evidence_id: "e1", claim: "Capacity rose", excerpt: "Ten percent" }],
          sources: [{ source_id: "s1", title: "Source", canonical_url: "https://example.com/" }],
        };
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  });
  vi.stubGlobal("fetch", fetchMock);

  const wrapper = mount(ResearchHistory);
  await wrapper.get("button").trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("Battery study");

  await wrapper.get(".history-link").trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("Archived report");
  expect(wrapper.text()).toContain("One source");
  expect(wrapper.text()).toContain("Capacity rose");
  expect(wrapper.get('a[href="https://example.com/"]').attributes("rel")).toBe("noopener noreferrer");
});
