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

- [x] 检索测试能返回相关 chunk，score 合理。
- [x] 跨租户数据不可见。
- [x] 返回 embedding/search 分项耗时。

## 产出物（G2 完成）

- `app/api/search.py` — `POST /search/test`：`tenant_id` **不入请求体**，取自认证身份（MVP stub 固定租户，stage 3 换真认证后依旧服务端强制）。
- `app/services/search_service.py` — `search_test`：E1 embedder 生成 query 向量（`perf_counter` 分项计时）→ Qdrant `query_points` 检索 → hits（`score/text/doc_id/version/page/metadata`）+ `took_embedding_ms/took_search_ms/took_total_ms`。
- **安全过滤（硬编码）**：`tenant_id` + `is_latest=true` + `is_deleted=false` 由 `_mandatory_filter` 构造，请求 `filters` 仅白名单键（`doc_id`/`access_level`/`chunk_index`）AND 追加——恶意键静默忽略，**结构性不可放宽**。
- `tests/test_g2_search.py` — 5 个离线用例（hits 字段/score 降序、三条件恒在、恶意 filters 不可放宽、分项耗时、路由注册 + 请求体无 tenant_id）。

## 实现说明（live E2E，真栈，real exit 0）

- 上传 → 流水线索引 → `search/test`："quarterly revenue growth" → **2 hits，top score=0.6507**，`embed=974.6ms / search=111.6ms` 分项。
- 隔离：异租户 id 检索 → **0 hits**；恶意 filters（伪造 tenant_id/is_latest/is_deleted）→ 仍 0 hits；白名单 `doc_id` 过滤正常 AND。
- 质量门禁：ruff/black/mypy（67 文件）零错误，pytest **239 passed**。

## 关联任务

- 依赖 [E](e2-qdrant-write.md)；被 [H4 检索测试页](h4-search-page.md) 使用。
