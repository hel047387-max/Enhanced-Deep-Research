export interface LiteratureMetadata {
  title: string;
  authors: string[];
  publication_year: number | null;
  doi: string | null;
  language: string | null;
  tags: string[];
}

export interface SearchableUnit extends LiteratureMetadata {
  unit_id: string;
  document_id: string;
  heading_path: string[];
  page_start: number | null;
  page_end: number | null;
  content_type: "paragraph" | "table" | "list" | "other";
  previous_unit_id: string | null;
  next_unit_id: string | null;
  text: string;
}

export interface LiteratureSearchItem extends SearchableUnit {
  similarity_score: number;
  rerank_score: number | null;
}

export interface LiteratureSearchResponse {
  items: LiteratureSearchItem[];
}

export interface IngestedDocument {
  document_id: string;
  units_indexed: number;
  metadata: LiteratureMetadata;
}

export interface LiteratureDocument extends LiteratureMetadata {
  document_id: string;
  units_indexed: number;
}

export interface LiteratureCitation {
  unit_id: string;
  document_id: string;
  title: string;
  authors: string[];
  publication_year: number | null;
  doi: string | null;
  heading_path: string[];
  page_start: number | null;
  page_end: number | null;
}

export interface LiteratureAnswer {
  answer: string;
  citations: LiteratureCitation[];
}

export interface LiteratureQueryOptions {
  limit?: number;
  document_ids?: string[];
  tags?: string[];
  language?: string;
  year_from?: number;
  year_to?: number;
}