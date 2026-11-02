# H5 · 设置页（MVP 最小）

> **阶段**：H 前端管理界面（5-6 天）　**依赖**：H1　**工时**：约 0.5 天

## 目标

提供默认配置的只读查看。

## 实施步骤

### 1. 页面 `frontend/src/pages/Settings/index.tsx`
- 查看默认 Embedding 模型配置（只读即可）。
- 查看切分参数（只读或简单可编辑）。

## 验收标准

- [x] 默认模型与切分参数可见。

## 产出物（H5 完成）

**后端新增只读端点**（此前无此接口，H5 补全）：

- `app/schemas/settings.py` — `EffectiveSettings{embedding_model, chunking}` + `EmbeddingModelOut`/`ChunkingOut`；
- `app/services/settings_service.py` — `get_effective_settings(db)`：默认 embedding 模型行（`is_default=True`）+ `settings.app.chunk_size/overlap`；
- `app/api/settings.py` — `GET /api/settings/effective`（FastAPI 路由注册于 `main.py`）；
- `tests/test_h5_settings.py` — 4 个离线测试（含 openapi 路由注册断言）。

**前端**：

- `src/pages/settings.tsx` — 双卡片只读：默认 Embedding 模型（名称/provider/模型名/维度/是否默认）+ 切分参数（chunk_size 512 / chunk_overlap 50 tokens）；
- `src/api/index.ts` — `EffectiveSettings` 类型 + `settingsApi.effective()`。

## 验收证据

| 层 | 证据 |
| :- | :--- |
| 离线 | `pytest tests/test_h5_settings.py` **4 passed**；全量 pytest **247 passed**（+4） |
| live | `GET /api/settings/effective` → `openai/qwen3.7-text-embedding-flash dim=1024`，chunking `{512, 50}`，real exit 0 |
| 前端 | `tsc --noEmit` 零错误 |

门禁：ruff 0 / black 全绿（96 文件）/ mypy 73 文件零错误。

## 关联任务

- 依赖 [H1](h1-frontend-init.md)。
