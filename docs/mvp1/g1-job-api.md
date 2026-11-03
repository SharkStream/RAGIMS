# G1 · 任务接口

> **阶段**：G 任务 / Chunk / 检索测试 API（3-4 天）　**依赖**：F　**工时**：约 1 天

## 目标

提供任务列表、详情、步骤与重试/取消接口。

## 实施步骤

### 1. 路由 `backend/app/api/jobs.py`
- `GET /jobs`：分页，按 `status`/`job_type` 过滤（走 `ingestion_jobs(tenant_id, status)` 索引）。
- `GET /jobs/{id}`：任务详情。
- `GET /jobs/{id}/steps`：步骤列表（含耗时、状态、错误），按 `step_order` 排序。
- `POST /jobs/{id}/retry`：失败任务重投。
- `POST /jobs/{id}/cancel`：标记取消。

## 验收标准

- [x] 任务列表与步骤可视化数据完整。
- [x] 重试/取消可用。

## 产出物（G1 完成）

- `app/api/jobs.py` — 5 个端点：`GET /jobs`（分页 + `status`/`job_type`/`doc_id` 过滤，走 `ingestion_jobs(tenant_id,status)` 索引）、`GET /jobs/{id}`、`GET /jobs/{id}/steps`（按 `step_order`，含 `duration_ms`）、`POST /jobs/{id}/retry`（201）、`POST /jobs/{id}/cancel`。
- `app/services/job_service.py` — `list_jobs`/`get_job_or_404`/`get_job_steps`/`retry_job`（仅 `failed` 可重投，其他 409；复制 `doc_version_id` + `job_type` 建**新 job 行**保留审计，再 dispatch）。
- `app/schemas/job.py` — `JobOut`/`JobStepOut`（含 `duration_ms`）/`JobRetryResponse`。
- `tests/test_g1_jobs.py` — 7 个离线用例（列表分页、租户隔离 404、步骤查询、retry 建新 job + dispatch + task_id 回写、非 failed 409、无 version 409、5 条路由注册）。

## 实现说明

- **重投语义**：不修改旧 job（失败历史保留），新建 pending job 复用原 `doc_version_id` → 幂等流水线重跑。
- **live E2E**（真 worker + broker，real exit 0）：① `GET /jobs?status=succeeded` → total=3 且目标 job 在页内；② 详情 `job_type=full` + `celery_task_id`；③ 步骤 7 条全有 `duration_ms` 与 output；④ 失败 PDF job → retry 201 → 新 job 派发且 `celery_task_id` 回写；⑤ 重投 succeeded job → 409；⑥⑦ 取消 pending → cancelled，再取消 → 409。
- 质量门禁：ruff/black/mypy（64 文件）零错误，pytest **234 passed**。

## 关联任务

- 依赖 [F 流水线](f2-pipeline.md)；被 [H3 任务看板](h3-job-board.md) 使用。
