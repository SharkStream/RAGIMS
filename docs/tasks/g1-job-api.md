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

- [ ] 任务列表与步骤可视化数据完整。
- [ ] 重试/取消可用。

## 关联任务

- 依赖 [F 流水线](f2-pipeline.md)；被 [H3 任务看板](h3-job-board.md) 使用。
