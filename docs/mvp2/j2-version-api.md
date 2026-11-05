# J2 · 版本查询 API

> **阶段**：J 版本与增量　**依赖**：J1　**工时**：约 0.5-1 天

## 目标

暴露文档的版本历史：列表（概要）与单版本详情（含该版本 chunks），为前端版本视图（J5）与回滚（J4）提供数据面。

## 实施步骤

1. `GET /api/documents/{doc_id}/versions?page=&page_size=` → `PageResult<DocumentVersionOut>`：
   - 字段：`version`、`content_hash`（前 12 位 + 全量可选）、`file_size`、`parse_status`、`chunk_count`、`embedding_model`、`is_latest`、`created_at`、`file_path`；
   - 排序 `version DESC`；租户校验沿用 `_get_doc_or_404` 语义（跨租户 404）。
2. `GET /api/documents/{doc_id}/versions/{version:int}` → `DocumentVersionDetail`：
   - 单版本全字段 + `chunks`（复用现有 chunk 列表逻辑，按 `doc_version_id` 而非 latest 过滤——现有 `GET /documents/{id}/chunks` 只看 current_version，保持不变，本接口补历史版本能力）。
3. schemas：`app/schemas/document.py` 加 `DocumentVersionOut` / `DocumentVersionDetail`（信封包 `ApiResponse`，与现有风格一致）。
4. OpenAPI 描述写清「version 为文档内序号，非全局 ID」。

## 验收标准

- [x] J1 造出的 v1/v2 文档：列表返回 2 行、`is_latest` 标注正确、倒序
- [x] 跨租户访问他人 doc → 404（`ERR_NOT_FOUND`）
- [x] 不存在的版本号 → 404
- [x] chunks 按请求的版本返回（历史版本可预览）
- [x] 单测覆盖分页/404/租户隔离；openapi 断言新路由

## 产出物（J2 完成）

| 位置 | 内容 |
| :-- | :-- |
| `app/api/documents.py` | 3 个新路由：`GET /documents/{id}/versions`（分页、version DESC）、`GET /documents/{id}/versions/{version}`（按文档内序号查详情）、`GET /documents/{id}/versions/{version}/chunks`（历史版本 chunks 预览，复用 ChunkOut 分页形状）；现有 `GET /documents/{id}/chunks`（只看 latest）保持不变 |
| `app/services/document_service.py` | `list_document_versions` / `get_document_version`（404 语义：doc 缺失/跨租户/序号不存在统一 `ERR_NOT_FOUND`）/ `list_version_chunks` |
| `app/schemas/document.py` | `DocumentVersionOut` 补 `embedding_model`（可空，兼容旧行）；detail 直接复用该 schema |

## 验收证据（live 探针 real exit 0）

| # | 场景 | 结果 |
| :- | :--- | :--- |
| 1 | 双版本文档列表 | 2 行、version DESC、v2 latest=true / v1 false、`file_path` 含 `/1/` `/2/` 段 |
| 2 | 按序号详情 + 缺失序号 | v1 详情 200；version=9 → 404 `ERR_NOT_FOUND` |
| 3 | 租户隔离 | 未知 doc → 404 |
| 4 | 历史版本 chunks | v1 与 v2 各自 chunk 列表独立，latest 端点 total 与 v2 一致（无回归） |

离线单测 `tests/test_j2_versions.py`：4 个（列表 DESC/字段、序号详情、404、版本 chunks 分页 + 参数转发）。

## 关联任务

- 依赖 [J1](j1-incremental-upload.md)；供 [J4](j4-version-switch.md)、[J5](j5-frontend-version-ui.md) 使用。
