# D6 · 阶段 D 验收标准

> **阶段**：D 解析、清洗、切分　**依赖**：D1–D5

## 验收清单

- [x] 三种格式样例均能产出非空 chunk 列表。
- [x] chunk 的 `token_count` 与 `chunk_size` 配置一致（±overlap）。
- [x] 解析失败可正确落库并可见错误信息。

## 验收记录（2026-10-23，远程 MySQL / MinIO，完整重演）

D5 已离线全验；本验收在**真库全链**重演（HTTP 上传 → 真MinIO raw-docs → 真库 parse_and_store → 内存 clean/chunk）：

1. **三格式非空 chunks**：pdf（3 blocks→3 chunks）/ docx（4→4）/ txt（1→1）——每格式 `parse_status='parsed'`、`parsed-text/{vid}.json` 落 MinIO 可回读、chunk_index 连续。
2. **token 一致性**：用 tiktoken **独立重编码**每个 chunk.text 复核 `token_count` 完全一致；全部满足 `0 < token_count ≤ 512`（默认配置 `settings.app` 读取），长块 chunk 满足 `> 50`（±overlap 下界；docx 短标题块按设计例外）。
3. **失败落库**：损坏 PDF → `parse_status='failed'` + `job_steps.error_message`（含 Traceback 摘要，用户可读）。
4. 质量门禁：ruff/black/mypy（54 文件）零错误，pytest **173 passed**。

## 达成标志

「上传文件 → 解析 → 清洗 → 切分」离线处理能力就绪，为 E 阶段向量化提供稳定输入。**阶段 D 完成** ✅

## 关联任务

- 上游：[D1](d1-parser-abstraction.md)–[D5](d5-unit-tests.md)。
- 下游：[E Embedding + Qdrant 入库](e1-embedding-client.md)。
