# M2 · 成本统计

> **阶段**：M 可观测与运维　**依赖**：[M1](m1-metrics.md)　**工时**：约 0.5 天

## 目标

embedding token 消耗可量化（plan 阶段 5「成本统计」），为监控大盘（M4）与容量规划供数。

## 实施步骤（完成 ✅）

1. **数据源修复（顺带发现的真实缺陷）**：pipeline embed 步骤原先把
   `(vectors, usage)` tuple 整体 repr 进 `job_steps.output`——不仅 token 记账丢失，
   **向量矩阵 repr 还撑爆了 output**。改为结构化 JSON 摘要：
   `{token_count, chunk_count, vector_dim, model}`，向量/usage 走进程内旁路。
2. `GET /api/stats/costs?days=30`（登录可读，租户隔离）：聚合 embed 步骤
   `output.token_count` —— `{total_tokens, embed_calls, days:[{day, tokens, embed_calls}]}`。
3. `ragims_embedding_tokens_total` gauge（M1）与成本 API 同源。

## 验收标准

- [x] 单测 4 例：聚合形状 / 空数据归零 / days 参数 422 / embed 输出契约（token 结构化 + 向量不入库）
- [x] F2 旧断言随新契约更新（`token_count`/`chunk_count`/无 vectors）
- [x] 门禁：pytest **365 passed**、ruff/black/mypy 全绿
- [x] live：`/stats/costs` 200（清空后新上传起 token 开始累计；旧数据的 embed 未结构化故为 0）

## 关联任务

- [M1](m1-metrics.md)（tokens gauge）、[M4](m4-dashboard.md)（成本曲线）。
