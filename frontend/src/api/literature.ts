import { apiFetch } from "./http";import type {
  IngestedDocument,
  LiteratureAnswer,
  LiteratureDocument,
  LiteratureMetadata,
  LiteratureQueryOptions,
  LiteratureSearchResponse,
} from "../types/literature";

const ROOT = "/api/v1/literature";

async function requestJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await apiFetch(input, init);
  return (await response.json()) as T;
}

export interface LiteratureApiClient {
  listDocuments(): Promise<LiteratureDocument[]>;
  uploadDocument(file: File, metadata?: Partial<LiteratureMetadata>): Promise<IngestedDocument>;
  searchLiterature(query: string, options?: LiteratureQueryOptions): Promise<LiteratureSearchResponse>;
  answerLiterature(query: string, options?: LiteratureQueryOptions): Promise<LiteratureAnswer>;
  deleteDocument(documentId: string): Promise<void>;
}

export const literatureApi: LiteratureApiClient = {
  listDocuments() {
    return requestJson<LiteratureDocument[]>(`${ROOT}/documents`);
  },

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
    await apiFetch(`${ROOT}/documents/${encodeURIComponent(documentId)}`, {
      method: "DELETE",
    });
  },
};