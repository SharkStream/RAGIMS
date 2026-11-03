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

- [ ] J1 造出的 v1/v2 文档：列表返回 2 行、`is_latest` 标注正确、倒序
- [ ] 跨租户访问他人 doc → 404（`ERR_NOT_FOUND`）
- [ ] 不存在的版本号 → 404
- [ ] chunks 按请求的版本返回（历史版本可预览）
- [ ] 单测覆盖分页/404/租户隔离；openapi 断言新路由

## 关联任务

- 依赖 [J1](j1-incremental-upload.md)；供 [J4](j4-version-switch.md)、[J5](j5-frontend-version-ui.md) 使用。
