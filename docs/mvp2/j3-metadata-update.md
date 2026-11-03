# J3 · 元数据更新 API（不重嵌入）

> **阶段**：J 版本与增量　**依赖**：MVP1（C2）　**工时**：约 0.5 天

## 目标

`PATCH /api/documents/{doc_id}` 更新文档元数据（title / tags / access_level / datasource_id），**只动 `documents` 一行，不产生任何 job、不碰 chunk 与向量**。

## 现状（MVP1 行为，需改）

- 无任何更新 API：title/tags 建后即固定；改元数据只能重新上传（触发全量重嵌入，浪费）。

## 实施步骤

1. `PATCH /api/documents/{doc_id}`，body 为 `DocumentPatchRequest`（全字段可选，至少一个）：
   - `title: str | None`（1-512 字符校验，复用上传时的约束）
   - `tags: list[str] | None`（整组替换，JSON 列）
   - `access_level: str | None`（枚举 internal/confidential/public，沿用 C1 定义）
   - `datasource_id: str | None`（存在性 + 租户校验，同上传逻辑）
2. 服务层 `update_document_meta(session, tenant_id, doc_id, patch) -> DocumentDetail`：
   - `session.get(Document)` + 租户校验（404 语义同 C2）；
   - 逐字段赋值（None 跳过，不支持置空 title）；`status == 'deleted'` 的文档 → 409 `ERR_CONFLICT`（删除态不可改）；
   - commit 后返回最新 `DocumentDetail`；**不 import workers、不 dispatch 任何任务**。
3. 错误映射：字段校验失败 422（Pydantic）、跨租户 404、删除态 409——全部走现有 `AppError`/全局 handler。
4. 审计留痕（轻量）：loguru 记录 `doc_id + 变更字段列表`（阶段 3 的 audit_logs 表延后，不在本任务）。

## 验收标准

- [ ] PATCH title/tags/access_level → 200 + Detail 返回新值；`ingestion_jobs` 无新行；chunks/版本行零变化
- [ ] 空 body / 未知字段 → 422
- [ ] 删除态文档 PATCH → 409；跨租户 → 404
- [ ] `tags` 整组替换语义（传 `["a"]` 后原 `["x","y"]` 消失）
- [ ] 单测覆盖；openapi 断言 `PATCH /documents/{doc_id}` 存在

## 关联任务

- 依赖 [C2](../mvp1/c2-document-query-api.md)；独立于 J1/J4 可并行；供 [J5](j5-frontend-version-ui.md) 的编辑表单调用。
