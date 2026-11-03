# C2 · 文档查询接口

> **阶段**：C 文档上传与元数据 API（3-4 天）　**依赖**：C1　**工时**：约 1 天

## 目标

实现文档的列表、详情、chunk 列表与软删除接口。

## 实施步骤

### 1. `GET /documents`
- 分页；过滤 `tenant_id`/`status`/`file_type`；标题关键字搜索（`LIKE`）。
- 走索引 `documents(tenant_id, status)`。

### 2. `GET /documents/{id}`
- 返回文档详情 + 最新版本信息（`is_latest=true` 的 `document_versions`）。
- 404 时返回统一错误码 `ERR_NOT_FOUND`。

### 3. `GET /documents/{id}/chunks`
- 先解析当前版本（`current_version`），再按 `chunks(doc_version_id, chunk_index)` 有序分页返回。
- 返回字段：`text`、`chunk_index`、`token_count`、`page`。

### 4. `DELETE /documents/{id}`
- MVP 软删除：`documents.status=deleted`（异步清理延后，见「MVP 不做」清单）。
- 若后续阶段引入版本，需同步置 `document_versions.is_deleted`。

### 5. 复用
- 分页结构用 [A3](a3-fastapi-skeleton.md) 的 `PageResult[T]`；`tenant_id` 来自 [A3](a3-fastapi-skeleton.md) 的 `get_current_user()`。

## 验收标准

- [x] 列表分页/过滤/搜索正确。
- [x] 详情返回最新版本信息。
- [x] chunk 列表按 `chunk_index` 有序分页。
- [x] 软删除后列表不再出现该文档（`status != deleted`）。

## 产出物（C2 完成）

- `app/services/document_service.py` 追加 — `list_documents`（强制 `tenant_id` 走 `idx_documents_tenant_status`；默认排除 `deleted`，显式传 `status` 可查删除项）、`get_document_or_404`（租户隔离 + 软删视为 404）、`get_latest_version`、`list_document_chunks`（当前版本 + `chunk_index` 有序分页）、`soft_delete_document`（`status='deleted'` + 同步置版本 `is_deleted=true`）。
- `app/api/documents.py` 追加 4 个路由 — `GET /documents`、`GET /documents/{id}`、`GET /documents/{id}/chunks`、`DELETE /documents/{id}`，全部统一 envelope + `PageResult` 分页。
- `app/schemas/document.py` 追加 — `DocumentOut` / `DocumentVersionOut` / `DocumentDetail` / `ChunkOut` / `DocumentDeleteResponse`。
- `tests/test_c2_query.py` — 9 个离线用例（envelope 形状、过滤转发、422 分页校验、404 envelope、chunks 字段形状、软删 envelope）。

## 实现说明

- **软删语义**：列表默认 `status != 'deleted'`；`GET` 详情与 chunks 对软删文档一律 404（对用户不可见）；`DELETE` 同时把该文档所有版本的 `is_deleted` 置 true（与 E2 检索过滤 `is_deleted=false` 对齐）。显式 `GET /documents?status=deleted` 可查删除项（管理视图）。
- **chunk 列表按 `current_version` 解析**（非简单 latest 标记），版本推进后自动跟随当前版本；`chunks` 表无 `is_deleted` 列，过滤职责在版本行。
- **live E2E**（真库，探针后零残留）：3 文档（pdf×2 + txt）+ 乱序插入 5 chunks → 列表过滤/搜索/分页全对；乱序插入的 chunks 跨页严格有序 `[0,1] [2,3] [4]`；详情带 latest_version；软删后列表/详情即隐、`status=deleted` 显式可查、版本行已标记。
- 质量门禁：ruff/black/mypy（42 文件）零错误，pytest **103 passed**。

## 关联任务

- 依赖 [C1](c1-upload-api.md)；被 [H2 文档页](h2-document-page.md) 使用。
