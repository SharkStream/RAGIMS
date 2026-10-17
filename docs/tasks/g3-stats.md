# G3 · 统计接口（MVP 最小）

> **阶段**：G 任务 / Chunk / 检索测试 API（3-4 天）　**依赖**：F　**工时**：约 0.5 天

## 目标

提供最小统计接口支撑看板。

## 实施步骤

### 1. 路由 `backend/app/api/stats.py`
- `GET /stats`：文档数、chunk 数、任务成功率、今日处理量。

## 验收标准

- [ ] 统计字段正确返回。

## 关联任务

- 依赖 [F](f2-pipeline.md)；被 [H5 设置页](h5-settings-page.md)（可选）使用。
