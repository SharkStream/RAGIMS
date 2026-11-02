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

- [x] 上传后任务自动流转至 success。
- [x] `job_steps` 每步有耗时与 output。
- [x] 人为制造解析失败，任务状态为 failed 且 error_message 可读。
- [x] 重试机制生效（mock 外部依赖失败验证）。

## 产出物（F2 完成）

- `app/workers/pipeline.py` — **全链编排**：`run_pipeline(doc_version_id)` 七步 chain（`parse → clean → chunk → persist_chunks → embed → upsert → write_back`，download 因文件已在 MinIO 由 parse 内部处理、index 可选步 MVP 跳过、finalize 并入末尾 `finish_job`）；每步包在 `record_step` 里（F1 基类）；跨步结果进程内传递（单 Celery task，无 broker 往返）；`ingest_document` 任务配 `autoretry_for=(Exception,), retry_backoff=2, retry_jitter=True, max_retries=3`（Celery 指数退避整链重试，幂等安全）。
- `app/workers/tasks.py` — 兼容 shim（C1 import 路径不变）；`celery_app.include` 指向 pipeline。
- `tests/test_f2_pipeline.py` — 7 个离线用例（DI 假件全链：七步顺序 + 全 succeeded + timing/output、parse 失败传播 + job failed + 可读 error、失败后链停止、autoretry 配置断言、契约名注册、step 顺序递增）。

## 实现说明

- **重试双层**：步内瞬时错误由 E1/E2 的 `with_backoff` 处理（秒级）；任务级 `autoretry` 处理跨服务故障（分钟级）——每次 Celery 重试都会留下新的 audit step 行（失败历史可查）。
- **幂等**：整链重跑安全（parse 覆盖 parsed-text 对象、insert_chunks 复用行、upsert 同 point id、write_back 普通 UPDATE）——E4 reconcile 兜底。
- **live E2E**（真 worker + 真 broker）：① 正常 txt → **7 步全 succeeded**，每步有 `started_at/finished_at` 耗时 + output（write_back 返回 `{"backfilled": N}`）；② 加密 PDF → parse 步 failed ×6 audit 行（autoretry 尝试历史）、`job.status=failed`、`error_message` 含 "password-protected" 可读。
- 质量门禁：ruff（含 scripts）/black/mypy（61 文件）零错误，pytest **219 passed**。

## 关联任务

- 依赖 [F1](f1-celery-base.md)；被 [F3 触发入口](f3-trigger.md)、[G1 任务接口](g1-job-api.md) 使用。
