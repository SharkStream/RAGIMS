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

- [ ] 批量 embedding 返回向量维度与 `dimension` 一致。
- [ ] 限流/5xx 触发指数退避重试（可 mock 验证）。
- [ ] token 数写入 `job_steps.output`。

## 关联任务

- 依赖 [D4 切分](d4-chunking.md)；被 [E2 Qdrant 写入](e2-qdrant-write.md)、[G2 检索测试](g2-search-test.md) 使用。
