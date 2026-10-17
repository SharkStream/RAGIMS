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

- [ ] 上传/重处理均能投递并关联 job。
- [ ] 取消标记可被 worker 识别。

## 关联任务

- 依赖 [F2](f2-pipeline.md)；被 [G1 任务接口](g1-job-api.md) 使用。
