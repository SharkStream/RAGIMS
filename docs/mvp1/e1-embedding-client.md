# E1 · Embedding 客户端

> **阶段**：E Embedding + Qdrant 入库（3-4 天）　**依赖**：D　**工时**：约 1 天

## 目标

封装 Embedding 调用：批量、限流、重试、Token 统计，配置从 `embedding_models` 表读取。

## 实施步骤

### 1. 接口 `backend/app/clients/embedder.py`
- `BaseEmbedder`（ABC）：`embed_batch(texts: list[str]) -> list[list[float]]`。
- `OpenAIEmbedder`：模型 `text-embedding-3-small`（`dimension=1536`），批量（如每批 64 条）。

### 2. 限流与重试
- 429 / 5xx 指数退避重试（复用统一重试工具）。
- 设置单批大小与并发上限，避免触发限流。

### 3. Token 统计
- 用 `tiktoken` 统计每批 token 数，写入 `job_steps.output`（供成本统计）。

### 4. 配置读取
- `dimension`、`model_name` 从 `embedding_models` 表读取（B2 种子预置默认模型）。

## 验收标准

- [x] 批量 embedding 返回向量维度与 `dimension` 一致。
- [x] 限流/5xx 触发指数退避重试（可 mock 验证）。
- [x] token 数写入 `job_steps.output`。

## 产出物（E1 完成）

- `app/utils/retry.py` — **统一重试工具**（可复用）：`with_backoff(fn, retries/base_delay/max_delay/retry_on|retry_when/sleep/jitter)`——指数退避（`base*2^n` 封顶 `max_delay`），sleep 注入使退避序列可断言；支持元组或谓词两种重试判定。
- `app/clients/embedder.py` — `BaseEmbedder`（`embed_batch` 按任务签名返回向量；`_slice_batches` 每批 64 条；`_validate` 校验**数量与维度**；`count_tokens` tiktoken cl100k；`embed_with_usage` 一并产出 `EmbeddingUsage`）；`OpenAIEmbedder`（OpenAI 兼容端点；`resp.data` 按 `index` **恢复输入顺序**——API 可能乱序返回）；`build_embedder_from_model(row)`（`model_name`/`dimension` 以 `embedding_models` 行为准，凭证/端点取 `settings.openai`）；`get_default_embedder(session)`（读 `is_default` 行，兜底第一行）。
- `tests/test_e1_embedder.py` — 13 个离线用例（批切 10→[4,4,2]、维度/数量校验、瞬时失败重试至成功（调用 3 次 + 退避序列 [0.5, 1.0]）、永久失败不重试、退避封顶序列 [5, 6, 6]、`_is_retryable` 对 429/500/400 的判定、usage dict 形状（即 F 写入 `job_steps.output` 的内容）、SDK mock 乱序恢复 + 调用参数、DB 行配置构造 + 非 openai provider 拒绝）。

## 实现说明

- **重试判定用谓词而非异常元组**：`_is_retryable` 统一处理 openai 异常族（`RateLimitError`/`APIConnectionError`/`InternalServerError` + `APIStatusError.status_code ∈ {429,500,502,503,504}`），400 等永久错误不重试直接上抛。
- **live E2E**（真库 + 真实 OpenAI 兼容 API）：种子行 `qwen3.7-text-embedding-flash (dim=1024)` → `get_default_embedder` 按行构造 → **真实调用 2 条文本 → 2×1024 维向量**、tokens=10 → `usage.to_output()` 写入真库 `job_steps.output` 回读一致。
- 质量门禁：ruff/black/mypy（56 文件）零错误，pytest **186 passed**。

## 关联任务

- 依赖 [D4 切分](d4-chunking.md)；被 [E2 Qdrant 写入](e2-qdrant-write.md)、[G2 检索测试](g2-search-test.md) 使用。
