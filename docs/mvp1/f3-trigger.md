# F3 · 触发入口

> **阶段**：F Celery 任务流水线（4-5 天）　**依赖**：F2　**工时**：约 1 天

## 目标

提供任务投递与重处理/取消入口。

## 实施步骤

### 1. 上传投递
- [C1](c1-upload-api.md) 上传成功后投递流水线任务，回写 `celery_task_id`。

### 2. 重新处理
- `POST /documents/{id}/reprocess`：创建新 job（`job_type=reprocess`）并投递。

### 3. 任务取消（MVP 可选）
- 标记 `cancelled`，worker 各步骤前检查中断标志。

## 验收标准

- [x] 上传/重处理均能投递并关联 job。
- [x] 取消标记可被 worker 识别。

## 产出物（F3 完成，F 阶段收官 = M2 后端闭环）

- `app/services/document_service.py` — `reprocess_document`（404 校验 → 取 `is_latest` 版本 → **新 job（`job_type=reprocess`）** → dispatch → `celery_task_id` 回写；复用 MinIO 里的原文件，无需重传）；`cancel_job`（仅 `pending/running` 可取消 → `cancelled`；终态 job → 409 `ERR_CONFLICT`；tenant 归属校验）。上传投递（C1 已有）本任务验收通过。
- `app/api/documents.py` — `POST /documents/{id}/reprocess`（201，返回 job_id）；`POST /documents/{id}/jobs/{job_id}/cancel`（200 `JobCancelResponse` / 409）。
- `app/workers/base.py` + `pipeline.py` — **取消识别**：`record_step` 在创建步骤行**之前**检查 `job.status == "cancelled"` → 抛 `PipelineCancelledError`（无 step 行、job 保持 cancelled）；`ingest_document` 用 `dont_autoretry_for=(PipelineCancelledError,)` 吞掉（**不触发重试**），返回 `{"status": "cancelled"}`。
- `tests/test_f3_trigger.py` — 8 个离线用例（reprocess 建 job + dispatch + task_id 回写、404、cancel 语义、终态 409、跨租户 404、**worker 识别**（cancelled → 0 step 行 + 状态保持）、running 不受影响、eager apply 吞取消）。

## 实现说明

- **确定性取消验证**：live 探针先造一个「已入队未派发」的 pending job → cancel API（200）→ `ingest_document.apply()` 进程内 eager 执行（等价 worker 任务体）→ 返回 `{"status":"cancelled"}`、**0 条 step 行**、job 状态保持 cancelled——无 broker 竞态。
- **live E2E**（真 worker + broker）：① 完成文档 → reprocess API → **新 reprocess job** → 七步全链重跑 → succeeded，`celery_task_id` 回写；② 终态 job cancel → 409。
- 质量门禁：ruff（含 scripts）/black/mypy（61 文件）零错误，pytest **227 passed**。

## 关联任务

- 依赖 [F2](f2-pipeline.md)；被 [G1 任务接口](g1-job-api.md) 使用。
