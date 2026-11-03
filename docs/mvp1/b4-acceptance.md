# B4 · 阶段 B 验收标准

> **阶段**：B 数据模型与存储层　**依赖**：B1、B2、B3

## 验收清单

- [x] `alembic upgrade head` 一键建出 9 张表（延后 6 张不建）。
- [x] 种子脚本可重复执行（幂等）。
- [x] 单测覆盖 Storage 封装（MinIO/Qdrant 容器或 mock）。
- [x] 关键索引就位：`documents(tenant_id,status)`、`document_versions UNIQUE(doc_id,content_hash)`、`chunks(doc_version_id,chunk_index)`、`chunks(doc_id)`、`ingestion_jobs(tenant_id,status)`、`job_steps(job_id,step_order)`。

## 验收记录（2026-10-22，远程 MySQL 8.0.45 / `ragims` 库，从空库完整重演）

1. **一键建表**：`alembic downgrade base`（10 表清空，仅余空 `alembic_version`）→ `alembic upgrade head` 一键重建恰好 9 张业务表 + `alembic_version`；`chunking_strategies` 等 6 张延后表不存在。同时验证了 downgrade 回滚路径。
2. **种子幂等**：`seed.py` 第 1 次 `+` 创建 tenant/admin/embedding model 各 1 行，第 2 次全部 `=` 跳过，零重复。
3. **Storage 单测**：全量 pytest **84 passed**（含 B3 的 18 个 fake 用例 + B2 的 44 个 DDL/元数据用例）。
4. **索引矩阵**（`information_schema` 断言，ALL OK）：
   - 6 个 MVP 关键索引精确匹配（列序一致）：5 个复合 + `uq_doc_versions_doc_content`；
   - 11 个 FK 全部 `RESTRICT/RESTRICT`，具名（`fk_*`）；
   - **FK 覆盖索引审计：每个 FK 列恰好 1 个覆盖索引**——6 列由复合/唯一索引前缀复用（如 `users.tenant_id ← uq_users_tenant_username`）、1 列显式单列（`chunks.doc_id ← idx_chunks_doc_id`）、4 列由 InnoDB 自动建（`fk_datasources_tenant`/`fk_documents_datasource`/`fk_jobs_doc`/`fk_jobs_doc_version`，无前缀可用时的标准行为），零冗余。

## 达成标志

表结构、迁移、存储封装全部就绪，支撑 M1「环境就绪」里程碑，后续 C–F 阶段的数据读写均基于此层。**M1 达成** ✅

## 关联任务

- 上游：[B1](b1-db-tables.md)、[B2](b2-orm-migration.md)、[B3](b3-storage-layer.md)。
- 下游：[C 文档上传与元数据 API](c1-upload-api.md)。
