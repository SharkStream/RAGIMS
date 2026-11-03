# E3 · MySQL 元数据写入

> **阶段**：E Embedding + Qdrant 入库（3-4 天）　**依赖**：E2　**工时**：约 0.5 天

## 目标

批量写入 `chunks` 表并更新版本统计，遵循「先 MySQL、再 Qdrant、最后回写 point_id」的顺序保证一致性。

## 实施步骤

### 1. 批量写 chunks
- 批量写入 `chunks`（`token_count`、`chunk_hash`、`metadata`）。

### 2. 更新版本统计
- 更新 `document_versions.chunk_count`、`embedding_model`。

### 3. 顺序约定（关键）
1. 先写 MySQL `chunks`；
2. 再写 Qdrant points（E2）；
3. 最后回写 `chunks.qdrant_point_id`。
- 任一步失败可重试/对账（E4）。

## 验收标准

- [x] chunks 表记录数正确，`chunk_count` 与 chunks 数一致。
- [x] 失败可重试，不产生孤儿数据。

## 产出物（E3 完成）

- `app/services/chunk_store.py` — `insert_chunks`（批量插 chunks，**按 `(doc_version_id, chunk_index)` 幂等**：已存在的 index 复用现有行，重试永不重复插；`ChunkDTO.metadata` → `meta` 列）；`finalize_version`（`chunk_count` + `embedding_model` 回填 version）；`write_back_point_ids`（按位置对齐回填 `qdrant_point_id`，数量不匹配拒绝）。
- `tests/test_e3_chunk_store.py` — 4 个离线用例（按位置对齐回填、数量不匹配拒绝、**与 E2 `point_id_for` 产出的 ID 一致**——F 组合两个服务时天然对齐、DTO metadata 映射）。

## 实现说明

- **顺序契约落位**（E3 step 3）：三步函数独立可重跑——`insert_chunks`（幂等 upsert 语义）→ E2 `upsert_doc_vectors`（同 ID 覆盖）→ `write_back_point_ids`（普通 UPDATE）。任一步失败后**整链重跑安全**：不产生重复行/重复点，E4 只需对账计数与 ID。
- **live E2E**（真库 + 真 Qdrant + 真实 API）完整重演：插入 1 chunk → 重复插入仍 1 行（幂等）→ `chunk_count=1`、`embedding_model=qwen3.7-text-embedding-flash` 回填 → Qdrant upsert + point_id 回填 → **全链重跑**：行数/点位/ID 全部稳定（无孤儿数据 ✓）。
- 质量门禁：ruff/black/mypy（58 文件）零错误，pytest **201 passed**。

## 关联任务

- 依赖 [E2](e2-qdrant-write.md)；被 [E4 一致性](e4-consistency.md) 保障。
