/**
 * Unified API client (H1 step 2).
 *
 * Wraps axios with the backend envelope contract: every response is
 * `{code, message, data}` — success code is "OK" (see app/schemas/common.py).
 * Non-OK codes and network errors surface as a single normalized ApiError
 * so pages only handle one rejection shape.
 */
import axios, { AxiosError } from "axios";

const baseURL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export interface ApiEnvelope<T> {
  code: string;
  message: string;
  data: T;
}

export class ApiError extends Error {
  code: string;
  status?: number;
  details?: unknown;

  constructor(code: string, message: string, status?: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export const http = axios.create({
  baseURL,
  timeout: 120_000, // uploads + retrieval test can be slow on cold models
});

http.interceptors.response.use(
  (response) => {
    const body = response.data as ApiEnvelope<unknown>;
    if (body && typeof body === "object" && "code" in body) {
      if (body.code !== "OK") {
        return Promise.reject(new ApiError(body.code, body.message, response.status));
      }
      // unwrap: pages receive `data` directly
      return body.data as never;
    }
    return response.data as never;
  },
  (error: AxiosError<ApiEnvelope<unknown>>) => {
    const body = error.response?.data;
    if (body && typeof body === "object" && "code" in body) {
      return Promise.reject(
        new ApiError(body.code, body.message, error.response?.status, body.data),
      );
    }
    return Promise.reject(
      new ApiError("ERR_NETWORK", error.message || "网络错误", undefined),
    );
  },
);

/** Friendly zh-CN copy for common error codes (H6 acceptance: 友好错误提示). */
const FRIENDLY: Record<string, string> = {
  ERR_VALIDATION: "输入有误，请检查后重试",
  ERR_NOT_FOUND: "资源不存在或已被删除",
  ERR_CONFLICT: "操作冲突：资源状态已变化",
  ERR_INTERNAL: "服务内部错误，请稍后重试",
  ERR_NETWORK: "网络异常：无法连接后端服务",
  ERR_FILE_TYPE: "不支持的文件类型",
  ERR_FILE_TYPE_NOT_ALLOWED: "仅支持 pdf / docx / txt 文件",
  ERR_FILE_TOO_LARGE: "文件超过大小上限",
  ERR_RATE_LIMITED: "请求过于频繁，请稍后重试",
};

/** One-liner message extraction for page-level error toasts. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const friendly = FRIENDLY[err.code];
    return friendly ?? `[${err.code}] ${err.message}`;
  }
  return String(err);
}
