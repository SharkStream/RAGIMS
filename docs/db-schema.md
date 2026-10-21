# B1 · 数据库表定义（MVP 子集，MySQL 8）

> 本文档是 [B1](tasks/b1-db-tables.md) 的核心产出物，也是 [B2 ORM 与迁移](tasks/b2-orm-migration.md) 的建模输入。
> 字段清单与 `plan.md` 第四节一致（含 B1 已回写的补充字段），延后的 6 张表不在此文档中建表（见文末「延后清单」）。
> 表结构最终以 Alembic 迁移为准；本文 DDL 用作模型定义的对照基线（B2 验收时逐表 `SHOW CREATE TABLE` 比对）。

---

## 1. 通用约定

| 约定 | 取值 | 说明 |
| :--- | :--- | :--- |
| 引擎 / 字符集 | `InnoDB` / `utf8mb4` / `utf8mb4_unicode_ci` | 与 A2 `deploy/mysql/init.sql` 建库参数一致 |
| 主键 | `id CHAR(36)` | UUID 字符串形式（`uuid4()` hex-dashed），MVP 直读友好，不用 `BINARY(16)` |
| 外键列 | `CHAR(36)` | 与主键同型；InnoDB 自动为 FK 列建索引（见 §4 索引说明，不重复建） |
| 时间列 | `DATETIME(3)`（毫秒精度） | **B1 决议**：不用 `TIMESTAMP`（2038 上限 + 隐式时区转换歧义）。DATETIME 无时区语义，应用层统一写 **UTC**；`created_at` 默认 `CURRENT_TIMESTAMP(3)`，`updated_at` 追加 `ON UPDATE CURRENT_TIMESTAMP(3)`（B2 的 `TimestampMixin` 用 server_default + onupdate 对应实现） |
| JSON 列 | MySQL 原生 `JSON` | MySQL JSON 列不支持字面量默认值，统一**可空**；初始值 `{}` / `[]` 由应用层写入 |
| 哈希列 | `CHAR(64)` | SHA-256 十六进制（`content_hash`、`chunk_hash`） |
| 状态列 | `VARCHAR(32)` + 注释枚举 | 不加 `CHECK` 约束（枚举值演进免迁移），合法性由 Pydantic schema 校验 |
| 删除策略 | 软删除 | `documents.status='deleted'` / `document_versions.is_deleted=true`；FK 全部 `ON DELETE RESTRICT`，MVP 无物理删除路径 |
| 布尔列 | `TINYINT(1)` | 即 MySQL `BOOLEAN` 别名 |

---

## 2. 表清单与建表顺序（FK 拓扑）

```
tenants → users → datasources → embedding_models → documents
        → document_versions → chunks → ingestion_jobs → job_steps
```

延后不建的 6 张：`chunking_strategies`、`parsers`、`permissions`、`audit_logs`、`evaluation_runs`、`quality_checks`。

---

## 3. 完整 DDL

### 3.1 tenants（预置一条默认租户）

```sql
CREATE TABLE tenants (
  id          CHAR(36)     NOT NULL                COMMENT 'UUID',
  name        VARCHAR(128) NOT NULL                COMMENT '租户名称',
  status      VARCHAR(32)  NOT NULL DEFAULT 'active' COMMENT 'active / disabled',
  created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='租户（MVP 仅预置一条默认租户）';
```

### 3.2 users（预置默认管理员）

```sql
CREATE TABLE users (
  id          CHAR(36)     NOT NULL                COMMENT 'UUID',
  tenant_id   CHAR(36)     NOT NULL                COMMENT '所属租户',
  username    VARCHAR(64)  NOT NULL                COMMENT '登录名（租户内唯一）',
  email       VARCHAR(255) NULL                    COMMENT '邮箱（MVP 可空）',
  role        VARCHAR(32)  NOT NULL DEFAULT 'admin' COMMENT 'admin / user（阶段 3 细化）',
  status      VARCHAR(32)  NOT NULL DEFAULT 'active' COMMENT 'active / disabled',
  created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_tenant_username (tenant_id, username),
  CONSTRAINT fk_users_tenant FOREIGN KEY (tenant_id)
    REFERENCES tenants (id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户（MVP 预置默认管理员）';
```

> `UNIQUE (tenant_id, username)` 为 B1 增补（plan.md §4.1 未列）：保证同一租户内用户名唯一，同时覆盖 `tenant_id` FK 所需索引。

### 3.3 datasources（MVP 仅实现 `local`）

```sql
CREATE TABLE datasources (
  id           CHAR(36)     NOT NULL                 COMMENT 'UUID',
  tenant_id    CHAR(36)     NOT NULL                 COMMENT '所属租户',
  name         VARCHAR(128) NOT NULL                 COMMENT '数据源名称',
  type         VARCHAR(32)  NOT NULL DEFAULT 'local' COMMENT 'MVP 仅 local；预留 s3/sharepoint/confluence/notion/feishu',
  config       JSON         NULL                     COMMENT '类型相关配置（local 为 {}）',
  sync_mode    VARCHAR(16)  NOT NULL DEFAULT 'manual' COMMENT 'manual / cron / webhook（MVP 仅 manual）',
  sync_cron    VARCHAR(64)  NULL                     COMMENT 'cron 表达式（sync_mode=cron 时使用，MVP 为 NULL）',
  last_sync_at DATETIME(3)  NULL,
  status       VARCHAR(32)  NOT NULL DEFAULT 'active' COMMENT 'active / disabled',
  created_at   DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at   DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  CONSTRAINT fk_datasources_tenant FOREIGN KEY (tenant_id)
    REFERENCES tenants (id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='数据源（MVP 仅 local 类型，上传时自动关联默认数据源）';
```

### 3.4 embedding_models（预置 OpenAI `text-embedding-3-small`）

```sql
CREATE TABLE embedding_models (
  id         CHAR(36)     NOT NULL               COMMENT 'UUID',
  name       VARCHAR(128) NOT NULL               COMMENT '展示名',
  provider   VARCHAR(32)  NOT NULL               COMMENT 'openai（MVP 唯一 provider）',
  model_name VARCHAR(128) NOT NULL               COMMENT 'text-embedding-3-small',
  dimension  INT          NOT NULL               COMMENT '向量维度（3-small=1536，Qdrant collection 对齐）',
  config     JSON         NULL                   COMMENT '批大小/超时/重试等 {"batch_size":64,"timeout_s":60,"max_retries":3}',
  is_default TINYINT(1)   NOT NULL DEFAULT 0     COMMENT '默认模型标记（MVP 恰好一条为 1）',
  PRIMARY KEY (id),
  UNIQUE KEY uq_embedding_models_provider_model (provider, model_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Embedding 模型配置（全局，不分租户）';
```

> - 该表**无 `created_at/updated_at`**：沿用 plan.md §4.6 清单（配置表，非业务数据）。
> - `UNIQUE (provider, model_name)` 为 B1 增补：防止重复登记同一模型，配合种子脚本「存在即跳过」双保险。

### 3.5 documents

```sql
CREATE TABLE documents (
  id             CHAR(36)      NOT NULL                  COMMENT 'UUID',
  tenant_id      CHAR(36)      NOT NULL                  COMMENT '所属租户（检索强制过滤）',
  datasource_id  CHAR(36)      NOT NULL                  COMMENT '来源数据源（上传时关联默认数据源）',
  external_id    VARCHAR(255)  NULL                      COMMENT '外部系统标识（MVP local 数据源为 NULL，阶段 2 同步用）',
  title          VARCHAR(512)  NULL                      COMMENT '标题（MVP 缺省取 file_name）',
  file_name      VARCHAR(255)  NOT NULL                  COMMENT '原始文件名',
  file_type      VARCHAR(16)   NOT NULL                  COMMENT 'pdf / docx / txt（MVP 仅此三种）',
  url            VARCHAR(1024) NULL                      COMMENT '来源 URL（本地文件为 NULL）',
  author         VARCHAR(128)  NULL,
  department     VARCHAR(128)  NULL,
  document_type  VARCHAR(64)   NULL                      COMMENT '业务分类（如 manual/spec/report，自由文本）',
  access_level   VARCHAR(32)   NOT NULL DEFAULT 'internal' COMMENT 'public / internal / confidential（写入 Qdrant payload）',
  tags           JSON          NULL                      COMMENT '字符串数组 ["tag1","tag2"]',
  current_version INT          NOT NULL DEFAULT 1        COMMENT '当前最新版本号',
  status         VARCHAR(32)   NOT NULL DEFAULT 'processing' COMMENT 'processing / active / deleted / failed',
  created_at     DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at     DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_documents_tenant_status (tenant_id, status),
  CONSTRAINT fk_documents_tenant FOREIGN KEY (tenant_id)
    REFERENCES tenants (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_documents_datasource FOREIGN KEY (datasource_id)
    REFERENCES datasources (id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='文档主表（软删除：status=deleted）';
```

### 3.6 document_versions

```sql
CREATE TABLE document_versions (
  id              CHAR(36)    NOT NULL                COMMENT 'UUID（幂等键之一）',
  doc_id          CHAR(36)    NOT NULL                COMMENT '所属文档',
  version         INT         NOT NULL                COMMENT '版本号（从 1 递增）',
  content_hash    CHAR(64)    NOT NULL                COMMENT '原始文件 SHA-256（幂等去重键）',
  file_path       VARCHAR(512) NOT NULL               COMMENT 'MinIO 对象键 raw-docs/{tenant_id}/{doc_id}/{version}/{filename}',
  file_size       BIGINT      NOT NULL DEFAULT 0      COMMENT '字节数',
  parse_status    VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT 'pending / processing / success / failed',
  chunk_count     INT         NOT NULL DEFAULT 0      COMMENT '切分完成的 chunk 数',
  embedding_model VARCHAR(128) NULL                   COMMENT '向量化使用的模型名（冗余自 embedding_models.model_name）',
  is_latest       TINYINT(1)  NOT NULL DEFAULT 1      COMMENT '是否该文档当前最新版本（检索强制过滤）',
  is_deleted      TINYINT(1)  NOT NULL DEFAULT 0      COMMENT '版本级软删除（检索强制过滤）',
  valid_from      DATETIME(3) NULL                    COMMENT '生效时间（NULL=随创建生效）',
  valid_to        DATETIME(3) NULL                    COMMENT '失效时间（NULL=仍有效）',
  created_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_doc_versions_doc_content (doc_id, content_hash),
  CONSTRAINT fk_doc_versions_doc FOREIGN KEY (doc_id)
    REFERENCES documents (id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='文档版本（幂等键 (doc_id, content_hash)）';
```

### 3.7 chunks

```sql
CREATE TABLE chunks (
  id              CHAR(36)     NOT NULL               COMMENT 'UUID',
  doc_version_id  CHAR(36)     NOT NULL               COMMENT '所属文档版本（幂等键之一）',
  doc_id          CHAR(36)     NOT NULL               COMMENT '所属文档（冗余，按文档直查免 join，并与 Qdrant payload 对齐）',
  version         INT          NOT NULL               COMMENT '文档版本号（冗余，与 Qdrant payload 对齐）',
  chunk_index     INT          NOT NULL               COMMENT '版本内顺序号，从 0 开始',
  text            MEDIUMTEXT   NOT NULL               COMMENT '切分文本（MEDIUMTEXT：TEXT 64KB 上限对超长段落/表格页不够，且无额外成本）',
  token_count     INT          NOT NULL DEFAULT 0     COMMENT 'tiktoken 计数',
  chunk_hash      CHAR(64)     NOT NULL               COMMENT 'SHA-256(text)，chunk 级幂等/去重',
  page            INT          NULL                   COMMENT '页码（docx/txt 可能无页码）',
  section         VARCHAR(255) NULL                   COMMENT '章节/标题路径',
  qdrant_point_id CHAR(36)     NULL                   COMMENT 'Qdrant point id（先写 MySQL，E3 阶段回写）',
  metadata        JSON         NULL                   COMMENT '附加信息 {bbox, heading, block_type, ...}',
  created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_chunks_version_index (doc_version_id, chunk_index),
  KEY idx_chunks_doc_id (doc_id),
  CONSTRAINT fk_chunks_doc_version FOREIGN KEY (doc_version_id)
    REFERENCES document_versions (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_chunks_doc FOREIGN KEY (doc_id)
    REFERENCES documents (id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Chunk 元数据（行不可变，只 insert；无 updated_at）';
```

### 3.8 ingestion_jobs

```sql
CREATE TABLE ingestion_jobs (
  id             CHAR(36)    NOT NULL                 COMMENT 'UUID',
  tenant_id      CHAR(36)    NOT NULL                 COMMENT '所属租户',
  doc_id         CHAR(36)    NULL                     COMMENT '目标文档（MVP 均填写；可空预留未来批量任务）',
  doc_version_id CHAR(36)    NULL                     COMMENT '目标版本（幂等键：避免同一版本重复处理）',
  job_type       VARCHAR(32) NOT NULL DEFAULT 'full'  COMMENT 'full / incremental / reprocess / delete',
  status         VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT 'pending / running / success / failed / cancelled',
  priority       INT         NOT NULL DEFAULT 5       COMMENT '0-9，数值越大越优先',
  created_by     CHAR(36)    NULL                     COMMENT '创建人 user id（不建 FK，用户删除不阻塞任务）',
  celery_task_id VARCHAR(64) NULL                     COMMENT 'Celery 任务 id（F 阶段 retry/cancel 关联）',
  created_at     DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  started_at     DATETIME(3) NULL,
  finished_at    DATETIME(3) NULL,
  error_message  TEXT        NULL,
  PRIMARY KEY (id),
  KEY idx_ingestion_jobs_tenant_status (tenant_id, status),
  CONSTRAINT fk_jobs_tenant FOREIGN KEY (tenant_id)
    REFERENCES tenants (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_jobs_doc FOREIGN KEY (doc_id)
    REFERENCES documents (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_jobs_doc_version FOREIGN KEY (doc_version_id)
    REFERENCES document_versions (id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='摄取任务（状态机 pending→running→success/failed/cancelled）';
```

### 3.9 job_steps

```sql
CREATE TABLE job_steps (
  id            CHAR(36)    NOT NULL                  COMMENT 'UUID',
  job_id        CHAR(36)    NOT NULL                  COMMENT '所属任务',
  step_order    INT         NOT NULL                  COMMENT '步骤序号（0..N，排序以此为准，不依赖时间戳）',
  step_name     VARCHAR(32) NOT NULL                  COMMENT 'download / parse / clean / chunk / embed / upsert / index / finalize',
  status        VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT 'pending / running / success / failed',
  retry_count   INT         NOT NULL DEFAULT 0        COMMENT '已重试次数（max_retries=3）',
  input         JSON        NULL                      COMMENT '步骤入参快照',
  output        JSON        NULL                      COMMENT '步骤产出（如 embedding token 统计）',
  started_at    DATETIME(3) NULL,
  finished_at   DATETIME(3) NULL,
  error_message TEXT        NULL,
  PRIMARY KEY (id),
  KEY idx_job_steps_job_order (job_id, step_order),
  CONSTRAINT fk_job_steps_job FOREIGN KEY (job_id)
    REFERENCES ingestion_jobs (id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='任务步骤（F2 流水线逐步回写状态/耗时/产出）';
```

---

## 4. 索引说明（对应 plan.md §4.9）

| 表 | 索引 | 来源 | 用途 |
| :--- | :--- | :--- | :--- |
| documents | `idx_documents_tenant_status (tenant_id, status)` | 显式 | 文档列表过滤分页；同时覆盖 `tenant_id` FK |
| document_versions | `UNIQUE uq_doc_versions_doc_content (doc_id, content_hash)` | 显式 | 幂等去重（C1 重复上传判定）；同时覆盖 `doc_id` FK |
| chunks | `idx_chunks_version_index (doc_version_id, chunk_index)` | 显式 | 按版本有序取 chunk；同时覆盖 `doc_version_id` FK |
| chunks | `idx_chunks_doc_id (doc_id)` | 显式 | 按文档取 chunk；同时覆盖 `doc_id` FK |
| ingestion_jobs | `idx_ingestion_jobs_tenant_status (tenant_id, status)` | 显式 | 任务列表过滤；同时覆盖 `tenant_id` FK |
| job_steps | `idx_job_steps_job_order (job_id, step_order)` | 显式 | 步骤时间线；同时覆盖 `job_id` FK |

要点：

- **FK 单列索引不重复建**。InnoDB 要求每个 FK 有以 FK 列为最左前缀的索引；上表显式复合索引已覆盖 `documents.tenant_id`、`document_versions.doc_id`、`chunks.doc_version_id`、`chunks.doc_id`、`ingestion_jobs.tenant_id`、`job_steps.job_id`，MySQL 不会为其额外建索引。仅 `users.tenant_id`、`datasources.tenant_id`、`ingestion_jobs.doc_id/doc_version_id` 由 InnoDB 自动补单列索引（无需手工声明）。
- **延后索引**（MVP 不建，与 plan.md §4.9 一致）：`documents(tenant_id, external_id)` 唯一、`document_versions(doc_id, version)` 唯一、`chunks(qdrant_point_id)`、`created_at` 降序索引。
- B2 的 `Index(tenant_id, status)` 等声明写在各模型 `__table_args__`，与本节一一对应。

---

## 5. 种子数据（B2 `scripts/seed.py` 输入，幂等：存在即跳过）

| 表 | 预置记录 |
| :--- | :--- |
| tenants | `id=00000000-0000-0000-0000-000000000001`、`name=default`、`status=active` |
| users | `id=00000000-0000-0000-0000-000000000002`、`tenant_id=<默认租户>`、`username=admin`、`email=admin@ragims.local`、`role=admin`、`status=active` |
| embedding_models | `provider=openai`、`model_name=text-embedding-3-small`、`dimension=1536`、`config={"batch_size":64,"timeout_s":60,"max_retries":3}`、`is_default=1` |

> 固定 UUID 与 `app/core/deps.py` 的 `DEFAULT_TENANT_ID` / `DEFAULT_USER_ID` 一致（A3 已锁定）。种子不进 Alembic 迁移，`upgrade head` 后单独执行。

---

## 6. 与 plan.md §4 的差异清单（均为 B1 决议，已回写或在此声明）

| 项 | 内容 | 原因 |
| :--- | :--- | :--- |
| 已回写 | `ingestion_jobs.celery_task_id` | F 阶段 retry/cancel 关联队列任务 |
| 已回写 | `job_steps.step_order` | 步骤排序不依赖时间戳 |
| 已回写 | `tenants/users/datasources` 补 `updated_at` | 通用约定统一 |
| 本文档 | 时间列 `TIMESTAMP` → `DATETIME(3)`，应用层写 UTC | 2038 上限、时区转换歧义 |
| 本文档 | 哈希列精确为 `CHAR(64)`、`chunks.text` 为 `MEDIUMTEXT` | MySQL 语义明确化 |
| 本文档 | `chunks` 仅 `created_at`（不可变行）、`embedding_models` 无时间戳（沿用 §4.6 清单） | 与 plan.md 逐表清单一致 |
| 本文档 | 增补 `UNIQUE(tenant_id, username)`（users）、`UNIQUE(provider, model_name)`（embedding_models） | 廉价的数据完整性约束 |
| 本文档 | `ingestion_jobs.doc_id/doc_version_id` 可空、`created_by` 不建 FK | 预留批量任务；用户删除不阻塞任务 |
| 本文档 | 状态列不加 `CHECK`，枚举值由应用层校验 | 枚举演进免 DDL 迁移 |

---

## 7. 延后清单（MVP 不建，防范围蔓延）

- 表：`chunking_strategies`（切分参数 MVP 硬编码 `chunk_size=512, overlap=50`）、`parsers`（解析器按 `file_type` 硬编码分派）、`permissions`、`audit_logs`（阶段 3）、`evaluation_runs`、`quality_checks`（阶段 4）。
- 索引：见 §4「延后索引」。
- 版本/权限相关字段已在现有列中**留位**：`document_versions.valid_from/valid_to/is_deleted`、`documents.access_level/external_id`。
