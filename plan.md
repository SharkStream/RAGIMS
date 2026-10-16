# 一、系统定位与边界

## 1.1 系统名称

**RAG Ingestion Management System**
中文：**知识库数据工程平台 / 文档处理与向量化管理系统**

## 1.2 核心目标

- 统一管理多源文档的接入、解析、切分、向量化和入库。
- 支持增量更新、版本切换、软删除、回滚。
- 支持多租户、权限过滤、审计。
- 提供任务调度、失败重试、质量检查、成本统计。
- 与在线检索服务解耦，保证重建索引不影响线上查询。

## 1.3 边界

**包含：**

- 数据源管理、文档上传、解析、清洗、切分、元数据抽取。
- Embedding 调用、Qdrant 写入、全文索引写入。
- 文档版本、增量、权限、任务、质量、监控。
- 管理界面和 API。

**不包含：**

- 在线问答生成、LLM 调用、Prompt 编排。
- 在线检索排序、重排、答案生成。
- 业务系统本身的权限体系，但会同步 ACL。

------

# 二、总体架构

text

```
┌─────────────────────────────────────────────────────────┐
│                      管理前端 / OpenAPI                   │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                    API 网关 / 管理服务                    │
│  认证、租户、数据源、文档、任务、配置、权限、监控接口       │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│              任务编排与调度（Temporal / Celery）           │
│   DAG：下载 → 解析 → 清洗 → 切分 → 向量化 → 入库 → 索引   │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                       Worker 集群                         │
│  解析 Worker | 清洗 Worker | 切分 Worker | 向量化 Worker  │
│  入库 Worker | 索引 Worker | 质量 Worker | 清理 Worker    │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                       存储层                              │
│  PostgreSQL：元数据、任务、版本、权限、配置               │
│  Qdrant：向量 + payload                                   │
│  MinIO/S3：原始文件、解析后文本、中间产物                  │
│  OpenSearch：全文索引                                     │
│  Redis：缓存、队列、分布式锁                              │
└─────────────────────────────────────────────────────────┘
```



------

# 三、核心模块设计

| 模块         | 职责                                                 | 关键能力                                   |
| :----------- | :--------------------------------------------------- | :----------------------------------------- |
| 数据源管理   | 接入本地、S3、SharePoint、Confluence、Notion、飞书等 | 全量/增量同步、定时任务、Webhook           |
| 文档管理     | 文档列表、详情、上传、删除、重新处理                 | 状态、版本、进度、预览                     |
| 解析与清洗   | PDF、DOCX、PPTX、XLSX、HTML、MD、TXT                 | OCR、表格提取、版面分析、去噪去重          |
| 切分与元数据 | 固定长度、递归字符、语义切分、父子块                 | chunk_size、overlap、标题/章节/页码        |
| 向量化       | 调用 Embedding 模型                                  | 批处理、限流、重试、Token 统计、成本核算   |
| 入库与索引   | 写入 Qdrant、OpenSearch、PostgreSQL                  | 版本化 upsert、payload 索引、全文索引      |
| 版本与增量   | content_hash、doc_id、version                        | is_latest、is_deleted、valid_from/to、回滚 |
| 权限与租户   | tenant_id、ACL、角色、用户                           | 检索强制过滤、权限变更即时生效             |
| 任务调度     | DAG 编排、任务队列、重试、死信                       | 状态机、幂等、断点续传、优先级             |
| 质量与评估   | 解析质量、chunk 质量、检索评估                       | 重复率、空块、抽样、A/B                    |
| 监控与运维   | 日志、指标、告警、成本                               | 任务成功率、耗时、积压、Token 消耗         |
| 管理界面     | 可视化操作                                           | 文档列表、任务看板、配置管理、检索测试     |

------

# 四、数据库表设计（PostgreSQL 元数据）

## 4.1 租户与用户

sql

```
tenants (
  id UUID PK,
  name VARCHAR,
  status VARCHAR,
  created_at TIMESTAMP
)

users (
  id UUID PK,
  tenant_id UUID FK,
  username VARCHAR,
  email VARCHAR,
  role VARCHAR,
  status VARCHAR,
  created_at TIMESTAMP
)
```



## 4.2 数据源

sql

```
datasources (
  id UUID PK,
  tenant_id UUID FK,
  name VARCHAR,
  type VARCHAR,          -- local, s3, sharepoint, confluence, notion, feishu
  config JSONB,
  sync_mode VARCHAR,     -- manual, cron, webhook
  sync_cron VARCHAR,
  last_sync_at TIMESTAMP,
  status VARCHAR,
  created_at TIMESTAMP
)
```



## 4.3 文档与版本

sql

```
documents (
  id UUID PK,
  tenant_id UUID FK,
  datasource_id UUID FK,
  external_id VARCHAR,
  title VARCHAR,
  file_name VARCHAR,
  file_type VARCHAR,
  url VARCHAR,
  author VARCHAR,
  department VARCHAR,
  document_type VARCHAR,
  access_level VARCHAR,
  tags JSONB,
  current_version INT,
  status VARCHAR,        -- active, deleted, processing, failed
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)

document_versions (
  id UUID PK,
  doc_id UUID FK,
  version INT,
  content_hash VARCHAR,
  file_path VARCHAR,
  file_size BIGINT,
  parse_status VARCHAR,
  chunk_count INT,
  embedding_model VARCHAR,
  is_latest BOOLEAN,
  is_deleted BOOLEAN,
  valid_from TIMESTAMP,
  valid_to TIMESTAMP,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)
```



## 4.4 Chunk 元数据

sql

```
chunks (
  id UUID PK,
  doc_version_id UUID FK,
  doc_id UUID FK,
  version INT,
  chunk_index INT,
  text TEXT,
  token_count INT,
  chunk_hash VARCHAR,
  page INT,
  section VARCHAR,
  qdrant_point_id VARCHAR,
  metadata JSONB,
  created_at TIMESTAMP
)
```



## 4.5 任务与步骤

sql

```
ingestion_jobs (
  id UUID PK,
  tenant_id UUID FK,
  doc_id UUID FK,
  doc_version_id UUID FK,
  job_type VARCHAR,      -- full, incremental, reprocess, delete
  status VARCHAR,        -- pending, running, success, failed, cancelled
  priority INT,
  created_by UUID,
  created_at TIMESTAMP,
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  error_message TEXT
)

job_steps (
  id UUID PK,
  job_id UUID FK,
  step_name VARCHAR,     -- download, parse, clean, chunk, embed, upsert, index, quality, switch
  status VARCHAR,
  retry_count INT,
  input JSONB,
  output JSONB,
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  error_message TEXT
)
```



## 4.6 配置表

sql

```
embedding_models (
  id UUID PK,
  name VARCHAR,
  provider VARCHAR,
  model_name VARCHAR,
  dimension INT,
  config JSONB,
  is_default BOOLEAN
)

chunking_strategies (
  id UUID PK,
  name VARCHAR,
  type VARCHAR,
  config JSONB,
  is_default BOOLEAN
)

parsers (
  id UUID PK,
  name VARCHAR,
  file_type VARCHAR,
  parser_class VARCHAR,
  config JSONB,
  is_default BOOLEAN
)
```



## 4.7 权限与审计

sql

```
permissions (
  id UUID PK,
  tenant_id UUID FK,
  resource_type VARCHAR,
  resource_id UUID,
  role_id UUID,
  user_id UUID,
  access_level VARCHAR
)

audit_logs (
  id UUID PK,
  tenant_id UUID FK,
  user_id UUID,
  action VARCHAR,
  resource_type VARCHAR,
  resource_id UUID,
  detail JSONB,
  created_at TIMESTAMP
)
```



## 4.8 质量与评估

sql

```
evaluation_runs (
  id UUID PK,
  tenant_id UUID FK,
  name VARCHAR,
  dataset JSONB,
  metrics JSONB,
  result JSONB,
  created_at TIMESTAMP
)

quality_checks (
  id UUID PK,
  doc_version_id UUID FK,
  check_type VARCHAR,
  score FLOAT,
  detail JSONB,
  created_at TIMESTAMP
)
```



------

# 五、API 接口清单

## 5.1 认证与租户

- `POST /auth/login`
- `GET /tenants`
- `POST /tenants`

## 5.2 数据源

- `GET /datasources`
- `POST /datasources`
- `POST /datasources/{id}/sync`
- `GET /datasources/{id}/status`

## 5.3 文档

- `POST /documents/upload`
- `GET /documents`
- `GET /documents/{id}`
- `DELETE /documents/{id}`
- `POST /documents/{id}/reprocess`
- `GET /documents/{id}/versions`
- `POST /documents/{id}/versions/{version}/rollback`
- `GET /documents/{id}/chunks`

## 5.4 任务

- `GET /jobs`
- `GET /jobs/{id}`
- `POST /jobs/{id}/retry`
- `POST /jobs/{id}/cancel`
- `GET /jobs/{id}/steps`

## 5.5 配置

- `GET/POST /embedding-models`
- `GET/POST /chunking-strategies`
- `GET/POST /parsers`

## 5.6 检索测试

- `POST /search/test`

## 5.7 权限

- `GET/POST /permissions`
- `GET /audit-logs`

## 5.8 监控

- `GET /metrics`
- `GET /stats`
- `GET /cost`

------

# 六、任务流水线设计

## 6.1 触发方式

- 手动上传
- 定时同步
- Webhook
- API 触发
- 重新处理

## 6.2 DAG 步骤

text

```
1. 接收/拉取文件
2. 计算 content_hash，判断是否需要更新
3. 创建 document_version，状态 pending
4. 解析：提取文本、表格、图片 OCR
5. 清洗：去噪、去重、标准化
6. 切分：按策略生成 chunks，计算 chunk_hash
7. 元数据抽取：标题、作者、部门、权限等
8. 向量化：批量调用 embedding，记录 token 消耗
9. 入库：Qdrant upsert points，写入 payload；元数据库存 chunk
10. 索引：OpenSearch 全文索引
11. 质量检查：抽样、重复率、空块检测
12. 版本切换：旧版本 is_latest=false，新版本 is_latest=true
13. 清理：异步删除旧版本（可选保留）
```



## 6.3 状态机

text

```
pending → running → success
                 → failed
                 → cancelled
```



## 6.4 重试策略

- 指数退避
- 最大重试次数
- 死信队列
- 幂等设计：相同 content_hash 不重复处理

------

# 七、技术选型

| 层级      | 推荐技术                               |
| :-------- | :------------------------------------- |
| 后端      | Python FastAPI + SQLAlchemy + Pydantic |
| 任务编排  | Temporal                               |
| 调度      | Temporal Schedules                     |
| 前端      | React + Ant Design Pro                 |
| 元数据库  | MYSQL                                  |
| 向量库    | Qdrant                                 |
| 对象存储  | MinIO / S3 / OSS                       |
| 全文索引  | OpenSearch                             |
| 缓存/队列 | Redis                                  |
| 监控      | Prometheus + Grafana + Loki            |
| 部署      | Docker + Kubernetes                    |
| CI/CD     | GitHub Actions + ArgoCD                |

------

# 八、详细实施 Plan

## 阶段 0：需求与设计（1-2 周）

**任务：**

- 需求调研、边界确认
- 数据模型设计、API 设计
- 技术选型、架构评审
- 项目计划、排期

**交付物：**

- PRD
- 架构图
- 数据库设计
- API 文档
- 项目计划

## 阶段 1：MVP（4-6 周）

**任务：**

- 项目脚手架、租户/用户
- 本地上传、PDF/DOCX/TXT 解析
- 固定切分、OpenAI Embedding
- Qdrant 入库、基础管理界面
- 任务队列、任务状态查看

**交付物：**

- 可上传文档并检索的 MVP
- 基础任务看板

## 阶段 2：版本与增量（3-4 周）

**任务：**

- content_hash、版本表
- 增量更新、软删除、回滚
- 重新处理、元数据变更不重嵌入
- 版本切换逻辑

**交付物：**

- 版本化文档管理
- 增量更新能力

## 阶段 3：权限与多租户（3-4 周）

**任务：**

- 租户隔离、ACL 同步
- 角色/用户权限
- 检索过滤、审计日志

**交付物：**

- 多租户权限系统
- 审计日志

## 阶段 4：质量与评估（2-3 周）

**任务：**

- 质量检查、重复检测
- 检索测试、评估指标
- 人工审核

**交付物：**

- 质量看板
- 评估报告

## 阶段 5：可观测与运维（2-3 周）

**任务：**

- 日志、指标、告警
- 任务监控、成本统计
- 备份恢复

**交付物：**

- 监控大盘
- 运维手册

## 阶段 6：优化与扩展（持续）

**任务：**

- 混合检索、多模态
- 图数据库、自动同步
- 性能优化、成本优化

**交付物：**

- 持续迭代

------

# 九、人员配置参考

| 角色            | 人数 | 职责                  |
| :-------------- | :--- | :-------------------- |
| 产品经理        | 1    | 需求、优先级、验收    |
| 项目经理        | 1    | 排期、协调、风险      |
| 后端工程师      | 2-3  | API、任务、存储、权限 |
| 前端工程师      | 1-2  | 管理界面              |
| 数据/算法工程师 | 1-2  | 解析、切分、Embedding |
| 测试工程师      | 1    | 功能、性能、集成      |
| 运维工程师      | 1    | 部署、监控、备份      |

------

# 十、风险与对策

| 风险         | 对策                                   |
| :----------- | :------------------------------------- |
| 解析质量差   | 多解析器、人工校正、质量评估           |
| 向量化成本高 | 缓存、批量、增量、模型选择             |
| 任务积压     | 队列分级、水平扩展、限流               |
| 版本混乱     | 强约束、幂等、审计                     |
| 权限漏洞     | 检索强制过滤、测试、审计               |
| 数据一致性   | 先写元数据再写向量，失败重试，对账任务 |
| 存储成本高   | 冷热分离、过期清理、压缩               |

------

# 十一、MVP 建议

先做最小闭环：

1. 本地上传 PDF/DOCX/TXT。
2. 解析文本。
3. 固定长度切分。
4. 调用 OpenAI Embedding。
5. 写入 Qdrant，payload 带 `doc_id`、`version`、`is_latest`、`tenant_id`、`access_level`。
6. 元数据写入 PostgreSQL。
7. 管理界面：文档列表、任务状态、Chunk 预览、检索测试。
8. 任务队列：Celery + Redis。

这个 MVP 大约 4-6 周可以跑通。后续再迭代版本、权限、质量、监控。