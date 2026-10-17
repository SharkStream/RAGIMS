# B2 · ORM 与迁移

> **阶段**：B 数据模型与存储层（2-3 天）　**依赖**：B1　**工时**：约 1 天

## 目标

用 SQLAlchemy 2.0 定义 9 个模型，Alembic 生成首版迁移，补齐 MVP 必需索引，并提供幂等种子脚本。

## 实施步骤

### 1. 模型基类 `backend/app/models/base.py`
- `Base`（`DeclarativeBase`）。
- `UUIDPkMixin`：`id` 用 `CHAR(36)` + `default=lambda: str(uuid4())`（MVP 直读友好，不用 `BINARY(16)`）。
- `TimestampMixin`：`created_at`/`updated_at`（`onupdate` 自动维护 `updated_at`）。

### 2. 9 个模型文件
- `tenant.py`、`user.py`、`datasource.py`、`embedding_model.py`、`document.py`、`document_version.py`、`chunk.py`、`ingestion_job.py`、`job_step.py`。
- 每个文件一个模型类，`__tablename__` 对应复数表名。
- JSON 列用 `sqlalchemy.JSON`（映射 MySQL `JSON`）。
- 外键 + `relationship`（MVP 可按需惰性加载，避免过度 eager）。

### 3. `models/__init__.py`
- 导入全部模型，保证 Alembic `autogenerate` 能发现所有表。

### 4. Alembic 初始化与首版迁移
- `alembic init alembic`，`alembic.ini` 指向 `core.config.settings.mysql_dsn`（`env.py` 读取）。
- `alembic revision --autogenerate -m "0001_initial"` 生成**单个初始迁移**，含 9 张表。
- 建表顺序由 FK 拓扑决定（父表先建）：`tenants → users → datasources → embedding_models → documents → document_versions → chunks → ingestion_jobs → job_steps`。
- 人工复核 autogenerate 产物，确认无遗漏列/索引。

### 5. MVP 必需索引（对应 plan.md 4.9）
在模型 `__table_args__` 中显式声明（FK 单列索引 InnoDB 自动建，**无需重复**）：
- `documents`：`Index(tenant_id, status)`
- `document_versions`：`UniqueConstraint(doc_id, content_hash)`（幂等去重）
- `chunks`：`Index(doc_version_id, chunk_index)`、`Index(doc_id)`
- `ingestion_jobs`：`Index(tenant_id, status)`
- `job_steps`：`Index(job_id, step_order)`

### 6. 种子脚本 `backend/scripts/seed.py`
- 幂等（存在即跳过）：默认租户、默认管理员、`embedding_models` 一条 `text-embedding-3-small`（`dimension=1536`、`is_default=True`）。
- **不进 Alembic 迁移**，`alembic upgrade head` 后单独执行，避免 `downgrade` 误删业务数据。

## 验收标准

- [ ] `alembic upgrade head` 一键建出 9 张表。
- [ ] `SHOW CREATE TABLE` 确认 6 个复合/唯一索引与 FK 就位，FK 单列索引未重复建。
- [ ] 种子脚本重复执行不产生重复租户/用户/模型。
- [ ] `created_at/updated_at` 自动维护生效。

## 关联任务

- 依赖 [B1](b1-db-tables.md)；被 [B3 存储层封装](b3-storage-layer.md) 与 [C1 上传接口](c1-upload-api.md) 依赖。
