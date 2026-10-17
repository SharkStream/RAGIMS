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

- [ ] chunks 表记录数正确，`chunk_count` 与 chunks 数一致。
- [ ] 失败可重试，不产生孤儿数据。

## 关联任务

- 依赖 [E2](e2-qdrant-write.md)；被 [E4 一致性](e4-consistency.md) 保障。
