# C3 · 数据源接口（MVP 最小）

> **阶段**：C 文档上传与元数据 API（3-4 天）　**依赖**：C1　**工时**：约 0.5 天

## 目标

提供数据源的最小 CRUD 占位，仅支持 `type=local`，并为上传自动关联默认数据源。

## 实施步骤

### 1. 路由 `backend/app/api/datasources.py`
- `GET /datasources`：列表。
- `POST /datasources`：仅允许 `type=local`，其他类型返回未实现错误。

### 2. 默认数据源
- 种子脚本（B2）预置一条默认 `local` 数据源。
- 上传接口（C1）未指定 `datasource_id` 时自动关联该默认数据源。

## 验收标准

- [x] `GET/POST /datasources` 可用，`type` 仅 `local`。
- [x] 上传时能自动关联默认数据源。

## 产出物（C3 完成）

- `app/api/datasources.py` — `GET /api/datasources`（租户内、最新在前）、`POST /api/datasources`（`type=local` 落库 201；其他类型 **501 `ERR_NOT_IMPLEMENTED`**；重名 409）。
- `app/services/datasource_service.py` — `list_datasources` / `create_local_datasource`（重名校验，DB 层未加唯一约束故由服务层守卫）。
- `app/schemas/datasource.py` — `DatasourceCreate`（`type` 默认 `local`）/ `DatasourceOut`。
- `scripts/seed.py` — 追加 `seed_default_datasource`：预置租户 `default`（`type=local`），幂等跳过。
- `tests/test_c3_datasources.py` — 6 个离线用例（schema 默认值、列表 envelope、201、501、409、422）。

## 实现说明

- **双层默认数据源兜底**：种子脚本预置（B2/C3 约定的主路径）+ `document_service._get_or_create_default_datasource` 运行时兜底（C1 已实现）——即使换了新租户或种子未跑，上传也不会失败。
- **501 而非 400**：非 `local` 类型是「规划中未实现」，用 501 + `ERR_NOT_IMPLEMENTED` 让前端能区分「参数错」与「功能未上线」。
- **live E2E**（真库）：seed 幂等（4 行全 `=` 跳过）；`GET` 列表含 `default`；`POST` local 201、重名 409、`s3` 501；**不带 `datasource_id` 上传 → 文档正确关联到种子默认数据源**。
- 质量门禁：ruff/black/mypy（45 文件）零错误，pytest **109 passed**。

## 关联任务

- 依赖 [C1](c1-upload-api.md)、种子脚本 [B2](b2-orm-migration.md)。
