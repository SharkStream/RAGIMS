# B4 · 阶段 B 验收标准

> **阶段**：B 数据模型与存储层　**依赖**：B1、B2、B3

## 验收清单

- [ ] `alembic upgrade head` 一键建出 9 张表（延后 6 张不建）。
- [ ] 种子脚本可重复执行（幂等）。
- [ ] 单测覆盖 Storage 封装（MinIO/Qdrant 容器或 mock）。
- [ ] 关键索引就位：`documents(tenant_id,status)`、`document_versions UNIQUE(doc_id,content_hash)`、`chunks(doc_version_id,chunk_index)`、`chunks(doc_id)`、`ingestion_jobs(tenant_id,status)`、`job_steps(job_id,step_order)`。

## 达成标志

表结构、迁移、存储封装全部就绪，支撑 M1「环境就绪」里程碑，后续 C–F 阶段的数据读写均基于此层。

## 关联任务

- 上游：[B1](b1-db-tables.md)、[B2](b2-orm-migration.md)、[B3](b3-storage-layer.md)。
- 下游：[C 文档上传与元数据 API](c1-upload-api.md)。
