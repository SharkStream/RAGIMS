# E5 · 阶段 E 验收标准

> **阶段**：E Embedding + Qdrant 入库　**依赖**：E1–E4

## 验收清单

- [ ] 样例文档全流程后，Qdrant 中 points 数与 `chunks` 表一致。
- [ ] payload 字段完整，`is_latest=true`。
- [ ] 相同文档重复处理不产生重复 points。

## 达成标志

文档向量化入库闭环完成，支撑 M2「后端闭环」里程碑（第 3 周末）。

## 关联任务

- 上游：[E1](e1-embedding-client.md)–[E4](e4-consistency.md)。
- 下游：[F Celery 流水线](f1-celery-base.md)、[G2 检索测试](g2-search-test.md)。
