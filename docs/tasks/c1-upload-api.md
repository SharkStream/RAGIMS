# C1 · 上传接口

> **阶段**：C 文档上传与元数据 API（3-4 天）　**依赖**：B　**工时**：约 1.5 天

## 目标

实现 `POST /documents/upload`：校验 → 计算哈希 → 存 MinIO → 落库（documents/document_versions）→ 建任务 → 投递 Celery，并保证幂等。

## 实施步骤

### 1. 路由 `backend/app/api/documents.py`
- `POST /documents/upload`（multipart）：`UploadFile` + 可选 `datasource_id`、`title`。
- 校验文件类型 `pdf/docx/txt`（扩展名 + MIME）与大小上限（如 50MB）。

### 2. Pydantic schema `backend/app/schemas/document.py`
- `DocumentUploadResponse`：`doc_id`、`version`、`job_id`、`status`、`duplicate`（幂等命中标记）。

### 3. 哈希工具 `backend/app/utils/hashing.py`
- `sha256_hex(data: bytes) -> str`。

### 4. 业务逻辑 `backend/app/services/document_service.py`
- `upload_document(file, tenant_id, datasource_id) -> ...`：
  1. 计算 `content_hash`。
  2. 幂等：按 `(doc_id, content_hash)` 查 `document_versions`，命中则返回已有 doc（`duplicate=true`，不重复投递）。
  3. 创建 `documents`（`status=processing`、`current_version=1`）与 `document_versions`（`version=1`、`is_latest=true`、`parse_status=pending`）。
  4. 上传原始文件到 MinIO：`raw-docs/{tenant_id}/{doc_id}/{version}/{filename}`，回写 `file_path`。
  5. 创建 `ingestion_jobs`（`job_type=full`、`status=pending`）。
  6. 投递 Celery 任务，回写 `celery_task_id`。

### 5. 事务边界
- 落库（documents/versions/job）在一个事务内；MinIO 上传失败则回滚并返回错误码。
- 幂等：相同 `content_hash` 已存在时返回已有 doc，或提示跳过。

## 验收标准

- [x] 上传 PDF/DOCX/TXT 均成功落库 + 落 MinIO。
- [x] 上传后能查到 `documents`、`document_versions`、`ingestion_jobs` 记录。
- [x] 重复上传相同文件触发幂等逻辑（`duplicate=true`）。
- [x] 有 Pydantic schema 校验与错误码（类型/大小超限返回明确错误）。

## 产出物（C1 完成）

- `backend/app/api/documents.py` — `POST /api/documents/upload`（multipart：`file` + 可选 `datasource_id`/`title`），薄路由，统一 envelope。
- `backend/app/services/document_service.py` — `validate_upload`（扩展名主判 + MIME 白名单 + 大小上限 `app.upload_max_mb=50`）与 `upload_document`（幂等 → 事务落库 + MinIO → Celery 投递）。
- `backend/app/schemas/document.py` — `DocumentUploadResponse`（`doc_id/version/job_id/status/duplicate/file_path/content_hash`）。
- `backend/app/utils/hashing.py` — `sha256_hex`。
- `backend/app/workers/` — 最小 Celery app + `ragims.ingest_document` 空任务占位（F1 完成流水线；broker 不可达时投递降级为 `celery_task_id=None` + 警告日志，上传不受阻）。
- `backend/tests/test_c1_upload.py` — 10 个离线用例（哈希向量、校验矩阵、schema、HTTP 层 stub service）。

## 实现说明与决策

- **幂等语义**：`(tenant_id, file_name, content_hash)` 命中非删除文档的 latest version → `duplicate=true`（返回既有 doc/job，不重传 MinIO、不重投递）。同内容**不同名**的文件视为有意上传，不拦截（保守，避免吞掉用户意图；全局内容级去重留给后续策略）。
- **默认数据源**：`documents.datasource_id` 是非空列而接口参数可选 → 未传时 get-or-create 租户 `default` 数据源（`type=local`）；传入的 `datasource_id` 会校验存在且属于当前租户（404）。
- **事务边界**：session autobegin 单事务 `documents + document_versions + ingestion_jobs`；MinIO 上传在事务内（C1 §5），失败 → rollback + 包装为 503 `ERR_UNAVAILABLE` envelope（E2E 已验证零残留）。投递在 commit 后（broker 故障不影响已落库数据）。
- **错误码**：415 `ERR_FILE_TYPE_NOT_ALLOWED`（扩展名或 MIME 不符）、413 `ERR_FILE_TOO_LARGE`（超限/空文件）、404 datasource、503 存储失败——全部走 A3 统一 envelope。
- **live E2E**（远程 MySQL/MinIO/Redis，探针后零残留）：上传 201 → DB 三行 + MinIO 字节回读一致 + `celery_task_id` 非空（broker 真实受理）；重传 `duplicate=true` 且行数不变 (1,1,1)；415/413 envelope 正确；MinIO 注入故障 → 503 + 回滚零行。

## 关联任务

- 依赖 [B 数据模型](b1-db-tables.md)；投递任务依赖 [F Celery 流水线](f1-celery-base.md)（MVP 先用空任务占位）。
- 被 [C2 文档查询](c2-document-query-api.md)、[H2 文档页](h2-document-page.md) 使用。
