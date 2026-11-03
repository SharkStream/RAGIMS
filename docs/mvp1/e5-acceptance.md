# E5 · 阶段 E 验收标准

> **阶段**：E Embedding + Qdrant 入库　**依赖**：E1–E4

## 验收清单

- [x] 样例文档全流程后，Qdrant 中 points 数与 `chunks` 表一致。
- [x] payload 字段完整，`is_latest=true`。
- [x] 相同文档重复处理不产生重复 points。

## 验收记录（E 阶段收官）

- **综合探针**（真库 + 真 Qdrant + 真实 API，PDF + TXT 双样例）：PDF 2 chunks / TXT 1 chunk 全链（上传→解析→清洗→切分→持久化→embed→upsert→回写）。
- ① points == chunks 行数（PDF 2==2，TXT 1==1）；② 回读 payload 含全字段（tenant/doc/version/access/chunk_index/page/chunk_hash/text）且 `is_latest=true`、`is_deleted=false` 过滤命中全量，chunk_hash 与库一致；③ purge + 同版本重跑 → points 不变（无重复）。
- 各子任务证据：[E1](e1-embedding-client.md)（维度/退避/token）、[E2](e2-qdrant-write.md)（幂等 upsert）、[E3](e3-mysql-metadata.md)（顺序契约/无孤儿）、[E4](e4-consistency.md)（purge/对账修复）。

## 达成标志

文档向量化入库闭环完成，支撑 M2「后端闭环」里程碑（第 3 周末）。

## 关联任务

- 上游：[E1](e1-embedding-client.md)–[E4](e4-consistency.md)。
- 下游：[F Celery 流水线](f1-celery-base.md)、[G2 检索测试](g2-search-test.md)。
