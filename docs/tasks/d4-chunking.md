# D4 · 切分

> **阶段**：D 解析、清洗、切分（4-5 天）　**依赖**：D3　**工时**：约 1 天

## 目标

定义切分器接口并实现固定长度（token）切分器，为每个 chunk 计算哈希与携带索引/页码。

## 实施步骤

### 1. Chunk 模型与接口 `backend/app/chunkers/base.py`
- `Chunk`（dataclass）：`chunk_index`、`text`、`token_count`、`page`、`metadata`、`chunk_hash`。
- `BaseChunker`（ABC）：`chunk(parsed: ParsedDocument, config) -> list[Chunk]`。

### 2. 固定长度切分器 `backend/app/chunkers/fixed_token_chunker.py`
- 用 `tiktoken` 按 token 切分，支持 `chunk_size`、`overlap`。
- 每个 chunk 计算 `chunk_hash`（text 的 SHA256，复用 [C1](c1-upload-api.md) 的 `utils/hashing.py`）。
- 携带 `chunk_index`、`page`（若可得）、`metadata`。

### 3. 默认配置
- 提供默认切分配置：`chunk_size=512`、`overlap=50`（MVP 硬编码，读 `Settings` 即可，不建 `chunking_strategies` 表）。

## 验收标准

- [ ] 三种格式清洗产物均产出非空 chunk 列表。
- [ ] chunk 的 `token_count` 与 `chunk_size` 一致（±overlap）。

## 关联任务

- 依赖 [D3](d3-cleaning.md)；被 [E1 Embedding](e1-embedding-client.md) 使用。
