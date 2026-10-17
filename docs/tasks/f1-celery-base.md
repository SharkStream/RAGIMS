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

- [ ] Celery 连接 Redis 正常，worker 可消费任务。
- [ ] 任务基类能正确记录 `job_steps` 与 `job` 状态。
- [ ] Flower 可访问。

## 关联任务

- 依赖 [C](c1-upload-api.md)/[D](d1-parser-abstraction.md)/[E](e1-embedding-client.md)；被 [F2 流水线编排](f2-pipeline.md) 使用。
