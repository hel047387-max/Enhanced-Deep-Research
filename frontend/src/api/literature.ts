import type {
  IngestedDocument,
  LiteratureAnswer,
  LiteratureMetadata,
  LiteratureQueryOptions,
  LiteratureSearchResponse,
} from "../types/literature";

const ROOT = "/api/v1/literature";

async function requestJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Keep the stable status message when the response is not JSON.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export interface LiteratureApiClient {
  uploadDocument(file: File, metadata?: Partial<LiteratureMetadata>): Promise<IngestedDocument>;
  searchLiterature(query: string, options?: LiteratureQueryOptions): Promise<LiteratureSearchResponse>;
  answerLiterature(query: string, options?: LiteratureQueryOptions): Promise<LiteratureAnswer>;
  deleteDocument(documentId: string): Promise<void>;
}

export const literatureApi: LiteratureApiClient = {
  async uploadDocument(file, metadata) {
    const body = new FormData();
    body.append("file", file);
    if (metadata) body.append("metadata_json", JSON.stringify(metadata));
    return requestJson<IngestedDocument>(`${ROOT}/documents`, { method: "POST", body });
  },

  searchLiterature(query, options = {}) {
    return requestJson<LiteratureSearchResponse>(`${ROOT}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, ...options }),
    });
  },

  answerLiterature(query, options = {}) {
    return requestJson<LiteratureAnswer>(`${ROOT}/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, ...options }),
    });
  },

  async deleteDocument(documentId) {
    const response = await fetch(`${ROOT}/documents/${encodeURIComponent(documentId)}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error(`Document deletion failed (${response.status}).`);
  },
};