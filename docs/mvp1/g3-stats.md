# G3 · 统计接口（MVP 最小）

> **阶段**：G 任务 / Chunk / 检索测试 API（3-4 天）　**依赖**：F　**工时**：约 0.5 天

## 目标

提供最小统计接口支撑看板。

## 实施步骤

### 1. 路由 `backend/app/api/stats.py`
- `GET /stats`：文档数、chunk 数、任务成功率、今日处理量。

## 验收标准

- [x] 统计字段正确返回。

## 产出物（G3 完成，G 阶段收官）

- `app/api/stats.py` + `app/services/stats_service.py` — `GET /stats`：`total_documents`（剔除 deleted）/ `total_chunks`（join 按租户）/ `total_jobs` / `succeeded_jobs` / `failed_jobs` / `processed_today`（UTC 当日起）/ `success_rate = succeeded/(succeeded+failed)`（无终态任务时 `null`）。
- `app/schemas/stats.py` — `StatsResponse`。
- `tests/test_g3_stats.py` — 4 个离线用例（字段 + 成功率 30/36、无终态 → null、零租户全 0、路由注册）。

## 实现说明（live E2E，真库，real exit 0）

- `GET /stats` 与 DB 直查**逐字段一致**（docs=3 chunks=1 jobs=3 ok=2 rate=1.0）。
- 上传 + 流水线成功后：docs+1、chunks+1、jobs+1、ok+1、today+1 —— 看板计数正确联动。
- 质量门禁：ruff/black/mypy（70 文件）零错误，pytest **243 passed**。

## 关联任务

- 依赖 [F](f2-pipeline.md)；被 [H5 设置页](h5-settings-page.md)（可选）使用。
