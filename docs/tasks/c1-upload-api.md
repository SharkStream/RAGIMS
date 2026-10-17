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

- [ ] 上传 PDF/DOCX/TXT 均成功落库 + 落 MinIO。
- [ ] 上传后能查到 `documents`、`document_versions`、`ingestion_jobs` 记录。
- [ ] 重复上传相同文件触发幂等逻辑（`duplicate=true`）。
- [ ] 有 Pydantic schema 校验与错误码（类型/大小超限返回明确错误）。

## 关联任务

- 依赖 [B 数据模型](b1-db-tables.md)；投递任务依赖 [F Celery 流水线](f1-celery-base.md)（MVP 可先用空任务占位）。
- 被 [C2 文档查询](c2-document-query-api.md)、[H2 文档页](h2-document-page.md) 使用。
