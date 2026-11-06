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
  datasource_id: string;
  access_level: string;
  tags: string[] | null;
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
  chunk_count: number;
  embedding_model: string | null;
  is_latest: boolean;
  created_at: string;
}

/** J3 metadata patch — all fields optional, null values are skipped. */
export interface DocumentPatch {
  title?: string;
  tags?: string[];
  access_level?: "internal" | "confidential" | "public";
  datasource_id?: string;
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
  /** J3 metadata-only update (no job, no re-embed). */
  patch: (docId: string, patch: DocumentPatch) =>
    http.patch<never, DocumentDetail>(`/documents/${docId}`, patch),
};

// ---- document versions (J2 list / J4 activate + reclaim) ----
export const documentVersionsApi = {
  list: (docId: string, params: { page?: number; page_size?: number }) =>
    http.get<never, PageResult<DocumentVersionOut>>(
      `/documents/${docId}/versions`,
      { params },
    ),
  /** Activate a historical version as latest (= rollback, no re-embed). */
  activate: (docId: string, version: number) =>
    http.post<never, DocumentDetail>(
      `/documents/${docId}/versions/${version}/activate`,
    ),
  /** Physically reclaim a non-latest version (chunks + points + objects). */
  remove: (docId: string, version: number) =>
    http.delete<never, { doc_id: string; version: number; status: string }>(
      `/documents/${docId}/versions/${version}`,
    ),
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

// ---- auth (K5) ----
export interface LoginResponse {
  token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: string;
    tenant_id: string;
    username: string;
    display_name?: string | null;
    role: string;
  };
}

export const authApi = {
  login: (username: string, password: string) =>
    http.post<never, LoginResponse>("/auth/login", { username, password }),
  me: () => http.get<never, LoginResponse["user"]>("/auth/me"),
};

// ---- user management (K7, admin-only) ----
export interface ManagedUser {
  id: string;
  tenant_id: string;
  username: string;
  email: string | null;
  role: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export const usersApi = {
  list: (params: { page?: number; page_size?: number; status?: string }) =>
    http.get<never, PageResult<ManagedUser>>("/auth/users", { params }),
  create: (body: {
    username: string;
    password: string;
    role: string;
    email?: string;
  }) => http.post<never, ManagedUser>("/auth/users", body),
  patch: (
    userId: string,
    body: { role?: string; status?: string; password?: string },
  ) => http.patch<never, ManagedUser>(`/auth/users/${userId}`, body),
};

// ---- quality & evaluation (L2/L3) ----
export interface QualityCheckOut {
  version: number;
  doc_version_id: string;
  check_type: string;
  score: number;
  detail: Record<string, unknown> | null;
  created_at: string | null;
}

export interface EvaluationSummary {
  id: string;
  name: string;
  parent_run_id: string | null;
  queries: number | null;
  metrics: Record<string, number> | null;
  created_at: string | null;
}

export interface EvaluationReport {
  id: string;
  name: string;
  parent_run_id: string | null;
  dataset: Array<{ query: string; expected_doc_ids: string[] }>;
  metrics: Record<string, number> | null;
  result: Array<{
    query: string;
    expected_doc_ids: string[];
    hit_doc_ids: string[];
    recallat_k?: number;
    "recall@k"?: number;
    reciprocal_rank?: number;
    "ndcg@k"?: number;
    first_hit_rank?: number;
    review?: { verdict: string; note?: string | null };
  }> | null;
  created_at: string | null;
}

export const qualityApi = {
  byDocument: (docId: string) =>
    http.get<never, QualityCheckOut[]>(`/documents/${docId}/quality`),
  listEvaluations: (params: { page?: number; page_size?: number }) =>
    http.get<never, PageResult<EvaluationSummary>>("/evaluations", { params }),
  evaluation: (runId: string) =>
    http.get<never, EvaluationReport>(`/evaluations/${runId}`),
  runEvaluation: (body: {
    name: string;
    top_k: number;
    dataset: Array<{ query: string; expected_doc_ids: string[] }>;
  }) => http.post<never, EvaluationReport>("/evaluations", body),
  reviewResult: (
    runId: string,
    index: number,
    body: { verdict: "correct" | "false_positive" | "missed"; note?: string },
  ) => http.patch<never, EvaluationReport>(`/evaluations/${runId}/results/${index}`, body),
};

// ---- observability (M1/M2/M3) ----
export interface HealthDetail {
  status: "ok" | "degraded";
  checks: Record<string, { ok: boolean; detail: string; elapsed_ms?: number }>;
  gauges: {
    documents_total: number;
    queue_depth: number;
    jobs_failed_24h: number;
    jobs_settled_24h: number;
  };
  alerts: Array<{ code: string; detail: string }>;
}

export interface CostSummary {
  total_tokens: number;
  embed_calls: number;
  days: Array<{ day: string; tokens: number; embed_calls: number }>;
}

export const opsApi = {
  healthDetail: () => http.get<never, HealthDetail>("/health/detail"),
  costs: (params: { days?: number }) =>
    http.get<never, CostSummary>("/stats/costs", { params }),
};
