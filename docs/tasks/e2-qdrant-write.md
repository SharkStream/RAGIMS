# E2 · Qdrant 写入

> **阶段**：E Embedding + Qdrant 入库（3-4 天）　**依赖**：E1、B3　**工时**：约 1 天

## 目标

将 chunk 向量批量 upsert 到 Qdrant，payload 完整、Point ID 确定、幂等。

## 实施步骤

### 1. Collection 初始化
- 复用 [B3](b3-storage-layer.md) `ensure_collection`：dimension 对齐模型（1536），`distance=COSINE`。

### 2. Payload 字段
- `tenant_id`、`doc_id`、`doc_version_id`、`version`、`is_latest`、`is_deleted`、`access_level`、`chunk_index`、`page`、`chunk_hash`、`text`（可选）。

### 3. Point ID 策略
- 确定性 ID：`uuid5(doc_version_id + chunk_index)`，便于幂等 upsert（同位置重复写覆盖而非新增）。

### 4. 批量 upsert
- 分批 `upsert_points`，失败重试（指数退避）。

### 5. 回写
- 成功后将 point id 回写 `chunks.qdrant_point_id`（E3 统一处理）。

## 验收标准

- [ ] payload 字段完整，`is_latest=true`。
- [ ] 相同文档重复处理不产生重复 points。
- [ ] Qdrant points 数与 chunks 表一致。

## 关联任务

- 依赖 [E1](e1-embedding-client.md)、[B3](b3-storage-layer.md)；被 [E3 MySQL 元数据](e3-mysql-metadata.md)、[E4 一致性](e4-consistency.md) 衔接。
