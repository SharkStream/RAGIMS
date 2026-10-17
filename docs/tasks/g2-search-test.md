# G2 · 检索测试接口

> **阶段**：G 任务 / Chunk / 检索测试 API（3-4 天）　**依赖**：E　**工时**：约 1.5 天

## 目标

提供管理界面的检索测试入口，强制租户隔离与版本过滤。

## 实施步骤

### 1. 路由 `backend/app/api/search.py`
- `POST /search/test`：入参 `{query, top_k, tenant_id, filters}`。

### 2. 服务 `backend/app/services/search_service.py`
- 用 [E1](e1-embedding-client.md) 生成 query 向量 → Qdrant `search`。
- 返回：`score`、`text`、`doc_id`、`version`、`page`、`metadata`。

### 3. 强制过滤（安全关键）
- `tenant_id` 过滤 + `is_latest=true` + `is_deleted=false`，硬编码在 filter 中，不可被请求覆盖。

### 4. 耗时统计
- 分项返回 embedding 耗时 / search 耗时。

## 验收标准

- [ ] 检索测试能返回相关 chunk，score 合理。
- [ ] 跨租户数据不可见。
- [ ] 返回 embedding/search 分项耗时。

## 关联任务

- 依赖 [E](e2-qdrant-write.md)；被 [H4 检索测试页](h4-search-page.md) 使用。
