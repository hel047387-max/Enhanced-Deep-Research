import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import LiteraturePanel from "./LiteraturePanel.vue";
import type { LiteratureApiClient } from "../api/literature";
import type { LiteratureSearchResponse } from "../types/literature";

function fakeApi(): LiteratureApiClient {
  return {
    listDocuments: vi.fn().mockResolvedValue([
      {
        document_id: "22222222-2222-4222-8222-222222222222",
        title: "RAG paper",
        authors: ["Author"],
        publication_year: 2025,
        doi: "10.1/example",
        language: "en",
        tags: ["RAG"],
        units_indexed: 2,
      },
    ]),
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
  it("shows an indeterminate progress bar while searching", async () => {
    const api = fakeApi();
    let finishSearch!: (value: LiteratureSearchResponse) => void;
    api.searchLiterature = vi.fn(() => new Promise<LiteratureSearchResponse>((resolve) => { finishSearch = resolve; }));
    const wrapper = mount(LiteraturePanel, { props: { api } });
    await flushPromises();

    await wrapper.get('[data-field="question"]').setValue("Find evidence");
    await wrapper.get('[data-action="search"]').trigger("click");

    const progress = wrapper.get('[role="progressbar"]');
    expect(progress.text()).toContain("Searching literature");
    expect(progress.attributes("aria-valuenow")).toBeUndefined();

    finishSearch({ items: [] });
    await flushPromises();
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false);
  });
  it("loads documents and sends the selection and result limit", async () => {
    const api = fakeApi();
    const wrapper = mount(LiteraturePanel, { props: { api } });
    await flushPromises();

    expect(wrapper.text()).toContain("RAG paper");
    await wrapper.get('[data-document-id="22222222-2222-4222-8222-222222222222"]').setValue(true);
    await wrapper.get('[data-field="result-limit"]').setValue("2");
    await wrapper.get('[data-field="question"]').setValue("What is hybrid retrieval?");
    await wrapper.get('[data-action="search"]').trigger("click");
    await flushPromises();

    expect(api.searchLiterature).toHaveBeenCalledWith("What is hybrid retrieval?", {
      document_ids: ["22222222-2222-4222-8222-222222222222"],
      limit: 2,
    });
  });

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
    expect(api.listDocuments).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("2 searchable units");
  });

  it("renders answer citations with pages", async () => {
    const api = fakeApi();
    const wrapper = mount(LiteraturePanel, { props: { api } });

    await wrapper.get('[data-field="question"]').setValue("What is hybrid retrieval?");
    await wrapper.get('[data-action="answer"]').trigger("click");
    await flushPromises();

    expect(api.answerLiterature).toHaveBeenCalledWith("What is hybrid retrieval?", {
      document_ids: [],
      limit: 3,
    });
    expect(wrapper.text()).toContain("Hybrid retrieval combines complementary signals.");
    expect(wrapper.text()).toContain("RAG paper");
    expect(wrapper.text()).toContain("Pages 12–13");
  });
});