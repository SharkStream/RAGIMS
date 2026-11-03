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

- [x] payload 字段完整，`is_latest=true`。
- [x] 相同文档重复处理不产生重复 points。
- [x] Qdrant points 数与 chunks 表一致。

## 产出物（E2 完成）

- `app/services/vectoring_service.py` — `point_id_for(doc_version_id, chunk_index)`（**uuid5 确定性 ID**，重处理覆盖同点位不新增）；`build_payload`（tenant_id/doc_id/doc_version_id/version/is_latest=true/is_deleted=false/access_level/chunk_index/page/chunk_hash/text——完整检索过滤集）；`upsert_doc_vectors`（`ensure_vector_collection(dimension)` → 128 点/批 `upsert_points` + `with_backoff` 瞬时重试 → 返回 point ids）。
- `tests/test_e2_vectoring.py` — 11 个离线用例（ID 确定性/隔离、payload 完整性、collection 维度对齐、批切 138→[128,10]、瞬时重试/永久上抛、数量不匹配拒绝、空输入 no-op、**重复 upsert 同 ID 集**（8 次写 4 个不同点）、payload-index 对应）。

## 实现说明

- **幂等核心**：Point ID 由 `uuid5(NAMESPACE_URL, "ragims:chunk:{version}:{index}")` 派生——同一版本的同一 chunk 永远同一 ID，重复处理是覆盖而非追加；live E2E 实测 upsert 两次 points 数不变。
- **顺序约定（E3 step 3）**：先 MySQL 后 Qdrant——`upsert_doc_vectors` 只管 Qdrant；`chunks.qdrant_point_id` 回写由 E3 统一处理（任务 step 5 约定），point id 可由 `point_id_for` 随时重算，对账无损。
- **live E2E**（真库 + 真 Qdrant + 真实 API）：上传→解析→清洗→切分→**chunks 表落行**（E3 雏形）→ 真实 embed（1 chunk, 200 tokens, dim=1024）→ upsert 两次 → points 1 == chunks 1（幂等 ✓）→ 搜索回读 payload：`is_latest=true`、tenant/doc/chunk_hash 与库一致。
- 质量门禁：ruff/black/mypy（57 文件）零错误，pytest **197 passed**。

## 关联任务

- 依赖 [E1](e1-embedding-client.md)、[B3](b3-storage-layer.md)；被 [E3 MySQL 元数据](e3-mysql-metadata.md)、[E4 一致性](e4-consistency.md) 衔接。
