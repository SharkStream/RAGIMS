# B3 · 存储层封装

> **阶段**：B 数据模型与存储层（2-3 天）　**依赖**：B2　**工时**：约 1 天

## 目标

封装 MinIO 与 Qdrant 客户端，统一 `StorageService`，隔离具体实现便于替换与单测。

## 实施步骤

### 1. MinIO 客户端 `backend/app/clients/minio_client.py`
- 方法：`upload_file(bucket, object_name, data_or_path)`、`download_file(bucket, object_name)`、`generate_presigned_url(bucket, object_name, expires)`、`delete_object(bucket, object_name)`。
- 从 `Settings` 读取 endpoint/access_key/secret_key。

### 2. Qdrant 客户端 `backend/app/clients/qdrant_client.py`
- 方法：`ensure_collection(collection_name, dimension, distance=COSINE)`、`upsert_points(points)`、`delete_by_filter(filter)`、`search(query_vector, filter, top_k)`。
- Point ID 策略：确定性 ID（`doc_version_id + chunk_index` 的 UUID5），便于幂等 upsert（E2 使用）。

### 3. 统一 `StorageService`（`backend/app/services/storage.py`）
- 组合 MinIO 与 Qdrant 客户端，对上层（workers/services）暴露语义化接口。
- 通过协议/抽象接口设计，便于在单测中用 mock 替换。

## 验收标准

- [x] 单测覆盖 Storage 封装（用 MinIO/Qdrant 容器或 mock）。
- [x] `ensure_collection` 幂等（已存在不报错）。
- [x] presigned URL 可访问对象。

## 产出物（B3 完成）

- `backend/app/clients/minio_client.py` — `MinioObjectStore`（`upload_file` 支持 bytes/本地路径、`download_file`、`generate_presigned_url`、`delete_object`、`ensure_bucket` 幂等、`object_exists`）；Minio 客户端可注入便于单测。
- `backend/app/clients/qdrant_client.py` — `QdrantVectorStore`（`ensure_collection` 幂等、`upsert_points`、`delete_by_filter` 返回删除前计数、`search`）+ `chunk_point_id()` 确定性 point id（`uuid5(固定命名空间, "{doc_version_id}:{chunk_index}")`，E2 幂等写入/版本回滚的基石）；旧 `app/clients/qdrant.py` 保留为兼容 shim。
- `backend/app/services/storage.py` — `ObjectStore`/`VectorStore` 两个 `Protocol` + `StorageService`（raw 文档对象键约定 `raw-docs/{tenant_id}/{doc_id}/{version}/{filename}`，C1/D2/E4 共用）+ `get_storage()` 惰性单例。
- `backend/tests/test_b3_storage.py` — 18 个离线用例（fake 注入，无网络依赖）。

## 实现说明

- **单测用 fake，不用容器**：`FakeMinio`/`FakeQdrant`（内存实现 + 调用录制）验证行为与参数转发；`runtime_checkable` Protocol 断言具体实现满足协议。CI 无需起容器。
- **真库 E2E 验证**（远程 MinIO + Qdrant，临时探针执行后清理）：上传 → presigned GET（HTTP 200 + 字节一致，5min 有效期）→ download 一致 → delete 后确认对象不存在；Qdrant `ensure_collection` 连续两次不报错（`documents`，dim=1024）→ 确定性 id upsert → 自查 score=1.0000 → `delete_by_filter` 删除 1 点、过滤计数归零，零残留。
- **qdrant-client API 适配**：新版移除 `client.search`，封装改用 `query_points`（返回 `.points`）；fake 同步。
- **语义**：`delete_by_filter` 先 `count(exact)` 再删（Qdrant 更新结果不含行数），供 E4 对账；`search` 的租户/`is_latest`/`is_deleted` 过滤由调用方（G2）组 Filter 传入，封装层不做隐藏过滤。

## 关联任务

- 依赖 [B2](b2-orm-migration.md)；被 [C1 上传](c1-upload-api.md)、[D2 解析](d2-format-parsers.md)、[E2 Qdrant 写入](e2-qdrant-write.md) 使用。
