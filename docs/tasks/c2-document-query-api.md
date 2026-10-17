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

- [ ] 列表分页/过滤/搜索正确。
- [ ] 详情返回最新版本信息。
- [ ] chunk 列表按 `chunk_index` 有序分页。
- [ ] 软删除后列表不再出现该文档（`status != deleted`）。

## 关联任务

- 依赖 [C1](c1-upload-api.md)；被 [H2 文档页](h2-document-page.md) 使用。
