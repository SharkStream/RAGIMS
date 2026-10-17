# F2 · 流水线编排

> **阶段**：F Celery 任务流水线（4-5 天）　**依赖**：F1　**工时**：约 2 天

## 目标

编排 DAG 步骤并维护任务/步骤状态机，支持失败重试与幂等。

## 实施步骤

### 1. Chain 编排 `backend/app/workers/pipeline.py`
- `download → parse → clean → chunk → embed → upsert → index(可选) → finalize`。
- MVP 本地文件可跳过 download（文件已在 MinIO）。

### 2. 每步记录
- 复用 [F1](f1-celery-base.md) 基类，更新 `job_steps.status/started_at/finished_at/output/error_message`（按 `step_order` 顺序）。

### 3. 状态机
- `ingestion_jobs`：`pending → running → success / failed`。

### 4. 失败重试
- 每步 `max_retries=3`，指数退避。

### 5. 幂等
- 以 `doc_version_id` 为幂等键，避免重复处理（配合 [E4](e4-consistency.md)）。

## 验收标准

- [ ] 上传后任务自动流转至 success。
- [ ] `job_steps` 每步有耗时与 output。
- [ ] 人为制造解析失败，任务状态为 failed 且 error_message 可读。
- [ ] 重试机制生效（mock 外部依赖失败验证）。

## 关联任务

- 依赖 [F1](f1-celery-base.md)；被 [F3 触发入口](f3-trigger.md)、[G1 任务接口](g1-job-api.md) 使用。
