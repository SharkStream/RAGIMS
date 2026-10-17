# F4 · 阶段 F 验收标准

> **阶段**：F Celery 任务流水线　**依赖**：F1–F3

## 验收清单

- [ ] 上传后任务自动流转至 success。
- [ ] `job_steps` 每步有耗时与 output。
- [ ] 人为制造解析失败，任务状态为 failed 且 error_message 可读。
- [ ] 重试机制生效（可 mock 外部依赖失败验证）。

## 达成标志

上传→解析→清洗→切分→embedding→Qdrant 全链路可在任务队列中自动执行，支撑 M2「后端闭环」。

## 关联任务

- 上游：[F1](f1-celery-base.md)–[F3](f3-trigger.md)。
- 下游：[G 任务/检索测试 API](g1-job-api.md)。
