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

- [ ] `GET/POST /datasources` 可用，`type` 仅 `local`。
- [ ] 上传时能自动关联默认数据源。

## 关联任务

- 依赖 [C1](c1-upload-api.md)、种子脚本 [B2](b2-orm-migration.md)。
