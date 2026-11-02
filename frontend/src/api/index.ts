/** Typed API calls — documents (C1/C2), jobs (G1), search (G2), stats (G3). */
import { http } from "./client";

export { http, ApiError, errorMessage } from "./client";

// ---- shared shapes (mirror backend schemas) ----
export interface DocumentOut {
  id: string;
  title: string;
  file_name: string;
  file_type: string;
  status: string;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentVersionOut {
  id: string;
  version: number;
  content_hash: string;
  file_path: string;
  file_size: number;
  parse_status: string;
  is_latest: boolean;
  created_at: string;
}

export interface DocumentDetail extends DocumentOut {
  latest_version: DocumentVersionOut | null;
}

export interface ChunkOut {
  chunk_index: number;
  text: string;
  token_count: number;
  page: number | null;
  section: string | null;
}

export interface UploadResponse {
  doc_id: string;
  version: number;
  job_id: string;
  status: string;
  duplicate: boolean;
  file_path: string;
  content_hash: string;
}

export interface JobOut {
  id: string;
  doc_id: string | null;
  job_type: string;
  status: string;
  celery_task_id: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobStepOut {
  step_order: number;
  step_name: string;
  status: string;
  duration_ms: number | null;
  output: Record<string, unknown> | null;
  error_message: string | null;
}

export interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface SearchHit {
  score: number;
  text: string;
  doc_id: string;
  version: number | null;
  page: number | null;
  metadata: Record<string, unknown>;
}

export interface SearchTestResponse {
  hits: SearchHit[];
  took_embedding_ms: number;
  took_search_ms: number;
  took_total_ms: number;
}

export interface StatsResponse {
  total_documents: number;
  total_chunks: number;
  total_jobs: number;
  succeeded_jobs: number;
  failed_jobs: number;
  processed_today: number;
  success_rate: number | null;
}

// ---- documents ----
export const documentsApi = {
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return http.post<never, UploadResponse>("/documents/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  /** Upload with progress callback + abort support (H2 upload UI). */
  uploadWithProgress: (
    form: FormData,
    onProgress: (percent: number) => void,
    signal?: AbortSignal,
  ) =>
    http.post<never, UploadResponse>("/documents/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e) => {
        if (e.total) onProgress(Math.round((e.loaded / e.total) * 100));
      },
      signal,
    }),
  reprocess: (docId: string) =>
    http.post<never, UploadResponse>(`/documents/${docId}/reprocess`),
  list: (params: {
    page?: number;
    page_size?: number;
    status?: string;
    file_type?: string;
    keyword?: string;
  }) => http.get<never, PageResult<DocumentOut>>("/documents", { params }),
  detail: (docId: string) => http.get<never, DocumentDetail>(`/documents/${docId}`),
  chunks: (docId: string, params: { page?: number; page_size?: number }) =>
    http.get<never, PageResult<ChunkOut>>(`/documents/${docId}/chunks`, { params }),
  remove: (docId: string) => http.delete<never, { doc_id: string }>(`/documents/${docId}`),
};

// ---- jobs (G1) ----
export const jobsApi = {
  list: (params: {
    page?: number;
    page_size?: number;
    status?: string;
    job_type?: string;
    doc_id?: string;
  }) => http.get<never, PageResult<JobOut>>("/jobs", { params }),
  detail: (jobId: string) => http.get<never, JobOut>(`/jobs/${jobId}`),
  steps: (jobId: string) =>
    http.get<never, PageResult<JobStepOut>>(`/jobs/${jobId}/steps`),
  retry: (jobId: string) =>
    http.post<never, { job_id: string; status: string }>(`/jobs/${jobId}/retry`),
  cancel: (jobId: string) =>
    http.post<never, { job_id: string; status: string }>(`/jobs/${jobId}/cancel`),
};

// ---- search (G2) ----
export const searchApi = {
  test: (body: { query: string; top_k?: number; filters?: Record<string, unknown> }) =>
    http.post<never, SearchTestResponse>("/search/test", body),
};

// ---- stats (G3) ----
export const statsApi = {
  get: () => http.get<never, StatsResponse>("/stats"),
};

// ---- settings (H5) ----
export interface EffectiveSettings {
  embedding_model: {
    id: string;
    name: string;
    provider: string;
    model_name: string;
    dimension: number;
    is_default: boolean;
  } | null;
  chunking: {
    chunk_size: number;
    chunk_overlap: number;
  };
}

export const settingsApi = {
  effective: () => http.get<never, EffectiveSettings>("/settings/effective"),
};
