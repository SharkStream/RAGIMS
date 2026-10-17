# RAG Ingestion Management System（RAGIMS）

文档摄取与向量化管理系统，当前处于 **MVP 规划/实施阶段**。

## 关键文档（按优先级读）

- `plan.md` — 总体设计；**第四节为数据库表设计（元数据库为 MySQL）**，第十一节为 MVP 范围
- `todolist.md` — MVP 阶段 A–I 拆解与「不做」清单
- `docs/tasks/README.md` — 41 个可执行 task 索引（每阶段一个链接表）
- `docs/tasks/*.md` — 每个 task 一个文件，含目标/实施步骤/验收标准/关联任务

## 技术栈

- 后端：FastAPI + SQLAlchemy 2.0 + Pydantic v2
- 任务：Celery + Redis（MVP 不用 Temporal）
- 元数据库：**MySQL 8**（utf8mb4）
- 向量库：Qdrant；对象存储：MinIO；全文索引：OpenSearch（MVP 不用）
- 前端：React + Vite + TypeScript + Ant Design Pro

## 关键约定

- 元数据库是 **MySQL 8**（不是 PostgreSQL）：UUID 主键用 `CHAR(36)`，JSON 列用 MySQL `JSON`
- MVP 只建 **9 张表**：`tenants / users / datasources / embedding_models / documents / document_versions / chunks / ingestion_jobs / job_steps`；`plan.md` 第四节标注「延后」的 6 张（`chunking_strategies / parsers / permissions / audit_logs / evaluation_runs / quality_checks`）不建
- MVP 必需索引（FK 列 InnoDB 自动建，无需重复）：`documents(tenant_id,status)`、`document_versions UNIQUE(doc_id,content_hash)`、`chunks(doc_version_id,chunk_index)`、`chunks(doc_id)`、`ingestion_jobs(tenant_id,status)`、`job_steps(job_id,step_order)`
- 检索强制过滤：`tenant_id` + `is_latest=true` + `is_deleted=false`，不可被请求覆盖
- 幂等：以 `content_hash`（唯一约束 `(doc_id, content_hash)`）与 `doc_version_id` 为幂等键

## 任务执行方式

用户指定 task 时（如「做 B2」「实现 docs/tasks/b2-orm-migration.md」），先读对应 `docs/tasks/` 文件，再顺其「关联任务」依赖链读上游，然后动手实现。阶段依赖：关键路径 A → B → D → E → F → G → I（H 可与 F/G 并行）。
