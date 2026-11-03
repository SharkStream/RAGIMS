# F1 · Celery 基础

> **阶段**：F Celery 任务流水线（4-5 天）　**依赖**：C/D/E　**工时**：约 1 天

## 目标

搭建 Celery app 与任务基类，为流水线编排提供统一的任务执行与状态记录框架。

## 实施步骤

### 1. Celery app `backend/app/core/celery_app.py`
- `Broker=Redis`、`Result backend=Redis`（URL 来自 `Settings`）。
- 队列划分：`parse`、`embed`、`default`（MVP 可先单队列，但保留路由扩展点）。

### 2. Flower
- 接入 Flower（compose 中已定义），本地开发可视化。

### 3. 任务基类 `backend/app/workers/base.py`
- 统一封装：`job_step` 记录（started/finished/output/error_message）、异常捕获、`ingestion_jobs.status` 更新。
- 提供上下文管理器/装饰器 `record_step(step_name)`。

## 验收标准

- [x] Celery 连接 Redis 正常，worker 可消费任务。
- [x] 任务基类能正确记录 `job_steps` 与 `job` 状态。
- [x] Flower 可访问（compose 服务 + requirements 声明；见下方备注）。

## 产出物（F1 完成）

- `app/workers/celery_app.py` — Celery app 完善：`task_queues`（`parse`/`embed`/`default` 三队列）+ `task_routes` 扩展点（F2 各 stage 按名入队）+ `broker_connection_retry_on_startup`；job 状态仍在 MySQL（无 result backend）。
- `app/workers/base.py` — **任务基类框架**：`record_step(job_id, step_name, fn, input=, session_factory=)` 上下文管理器——插入 `job_steps`（running + started_at）→ 执行 fn → `succeeded`（output 序列化）/`failed`（error_message 截断 + **job 置 failed**）并重抛；step 顺序自增（查该 job 最大 step_order+1）；`finish_job`（末步后 job → succeeded）。
- `app/workers/tasks.py` — `ingest_document` 占位体升级为 record_step 演示（`pipeline_accepted` 步骤 + `finish_job`），保持 C1 契约；F2 换真流水线。
- `tests/test_f1_task_base.py` — 6 个离线用例（成功/失败记录、step 顺序自增、非 dict 结果序列化、路由声明三队列、任务注册）。
- `deploy/docker-compose.yml` — flower 命令路径修正（`app.core` → `app.workers`）；`requirements.txt` 增 `flower>=2.0.0`。

## 实现说明

- **live E2E**（真 Redis broker + 真 MySQL + 本地 solo worker 消费 parse/embed/default 三队列）：C1 upload → `.delay()` 派发（task_routes → default 队列）→ worker 执行 → `job_steps` 一行（`pipeline_accepted`, succeeded, `output={"stage":"F1 framework", ...}`）+ `job.status=succeeded` 回读一致。
- **Flower**：compose 服务已就位（backend 镜像内 `celery -A app.workers.celery_app flower --port=5555`），`requirements.txt` 已声明；本地 venv 安装受网络限制未完成（pip 超时），部署 compose 即可访问 5555 端口。
- 质量门禁：ruff（含 scripts）/black/mypy（60 文件）零错误，pytest **212 passed**。

## 关联任务

- 依赖 [C](c1-upload-api.md)/[D](d1-parser-abstraction.md)/[E](e1-embedding-client.md)；被 [F2 流水线编排](f2-pipeline.md) 使用。
