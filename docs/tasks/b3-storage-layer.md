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

- [ ] 单测覆盖 Storage 封装（用 MinIO/Qdrant 容器或 mock）。
- [ ] `ensure_collection` 幂等（已存在不报错）。
- [ ] presigned URL 可访问对象。

## 关联任务

- 依赖 [B2](b2-orm-migration.md)；被 [C1 上传](c1-upload-api.md)、[D2 解析](d2-format-parsers.md)、[E2 Qdrant 写入](e2-qdrant-write.md) 使用。
