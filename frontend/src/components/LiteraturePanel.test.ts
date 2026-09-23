import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import LiteraturePanel from "./LiteraturePanel.vue";
import type { LiteratureApiClient } from "../api/literature";

function fakeApi(): LiteratureApiClient {
  return {
    uploadDocument: vi.fn().mockResolvedValue({
      document_id: "22222222-2222-4222-8222-222222222222",
      units_indexed: 2,
      metadata: { title: "RAG paper", authors: [], publication_year: null, doi: null, language: null, tags: [] },
    }),
    searchLiterature: vi.fn().mockResolvedValue({ items: [] }),
    answerLiterature: vi.fn().mockResolvedValue({
      answer: "Hybrid retrieval combines complementary signals.",
      citations: [{
        unit_id: "11111111-1111-4111-8111-111111111111",
        document_id: "22222222-2222-4222-8222-222222222222",
        title: "RAG paper",
        authors: ["Author"],
        publication_year: 2025,
        doi: "10.1/example",
        heading_path: ["Methods"],
        page_start: 12,
        page_end: 13,
      }],
    }),
    deleteDocument: vi.fn().mockResolvedValue(undefined),
  };
}

describe("LiteraturePanel", () => {
  it("uploads a document and shows the indexed unit count", async () => {
    const api = fakeApi();
    const wrapper = mount(LiteraturePanel, { props: { api } });
    const file = new File(["paper"], "paper.pdf", { type: "application/pdf" });

    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", { value: [file] });
    await input.trigger("change");
    await wrapper.get('[data-action="upload"]').trigger("click");
    await flushPromises();

    expect(api.uploadDocument).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain("2 searchable units");
  });

  it("renders answer citations with pages", async () => {
    const wrapper = mount(LiteraturePanel, { props: { api: fakeApi() } });

    await wrapper.get('[data-field="question"]').setValue("What is hybrid retrieval?");
    await wrapper.get('[data-action="answer"]').trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Hybrid retrieval combines complementary signals.");
    expect(wrapper.text()).toContain("RAG paper");
    expect(wrapper.text()).toContain("Pages 12–13");
  });
});