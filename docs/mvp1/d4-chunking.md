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

- [x] 三种格式清洗产物均产出非空 chunk 列表。
- [x] chunk 的 `token_count` 与 `chunk_size` 一致（±overlap）。

## 产出物（D4 完成，D 阶段收官）

- `app/chunkers/base.py` — `Chunk`（`chunk_index/text/token_count/page/metadata/chunk_hash`）、`ChunkerConfig`（frozen；默认值读 `Settings.app.chunk_size/chunk_overlap`；非法配置 → `ValueError`）、`BaseChunker` ABC、`DEFAULT_CHUNKER_CONFIG`。
- `app/chunkers/fixed_token_chunker.py` — `FixedTokenChunker`：tiktoken（`cl100k_base`，本地缓存离线可用）**逐 block 滑窗**（不跨 block，chunk 的 `page` 精确）；`chunk_hash` = `sha256_hex(text)`（复用 C1 hashing）；`metadata` 带 `block_type`。
- `app/core/config.py` — `chunk_size=512`、`chunk_overlap=50`（D4 step 3：不建 `chunking_strategies` 表）。
- `tests/test_d4_chunking.py` — 15 个离线用例（配置守卫、窗口不变量参数化扫描、overlap 边界 token 复现、跨 block 隔离、hash 一致性、不可变性、空文档、三格式 parse→clean→chunk 集成）。

## 实现说明

- **窗口不变式**：满窗恒 = `chunk_size`；多窗 block 的尾窗长度 ∈ `(overlap, chunk_size]`（由步长 = `chunk_size − overlap` 数学保证）——初版「尾窗折叠」分支经推导是死代码，已删除。
- **短块例外（正确行为）**：短于一个窗口的 block（如 docx 标题 "Chunk Source"=2 tokens）整块产出，不受下界约束——标题不可丢；测试按 block 长度区分断言。
- **离线三格式集成验收**：pdf（3 blocks→12 chunks）/ docx（3→6）/ txt（1→6），每 chunk `0 < token_count ≤ chunk_size`，index 连续，hash 齐。
- 质量门禁：ruff/black/mypy（54 文件）零错误，pytest **162 passed**。

## 关联任务

- 依赖 [D3](d3-cleaning.md)；被 [E1 Embedding](e1-embedding-client.md) 使用。
