# MVP Task 文档索引

> 由 `todolist.md` 展开的可执行级 task 文档，每任务一个文件。共 9 个阶段、41 个任务。
> 阶段依赖与预估工时见 `todolist.md` 总览；关键路径 **A → B → D → E → F → G → I**（H 可与 F/G 并行）。

## 阶段 A · 项目脚手架与基础设施（3-4 天）

| 任务 | 文件 | 说明 |
| :--- | :--- | :--- |
| A1 | [仓库与工程结构](a1-repo-structure.md) | monorepo、目录分层、日志/配置/规范 |
| A2 | [本地开发环境](a2-local-env.md) | docker-compose、MySQL/MinIO/Qdrant 初始化 |
| A3 | [FastAPI 骨架](a3-fastapi-skeleton.md) | 入口、健康检查、统一响应、依赖 |
| A4 | [验收标准](a4-acceptance.md) | 阶段 A 达成标志 |

## 阶段 B · 数据模型与存储层（2-3 天）

| 任务 | 文件 | 说明 |
| :--- | :--- | :--- |
| B1 | [数据库表（MVP 子集）](b1-db-tables.md) | 9 张必需表、延后 6 张 |
| B2 | [ORM 与迁移](b2-orm-migration.md) | SQLAlchemy 模型、Alembic、索引、种子 |
| B3 | [存储层封装](b3-storage-layer.md) | MinIO / Qdrant 客户端 |
| B4 | [验收标准](b4-acceptance.md) | 阶段 B 达成标志 |

## 阶段 C · 文档上传与元数据 API（3-4 天）

| 任务 | 文件 | 说明 |
| :--- | :--- | :--- |
| C1 | [上传接口](c1-upload-api.md) | multipart、哈希、MinIO、幂等 |
| C2 | [文档查询接口](c2-document-query-api.md) | 列表/详情/chunk/软删除 |
| C3 | [数据源接口](c3-datasource-api.md) | 仅 local、默认数据源 |
| C4 | [验收标准](c4-acceptance.md) | 阶段 C 达成标志 |

## 阶段 D · 解析、清洗、切分（4-5 天）

| 任务 | 文件 | 说明 |
| :--- | :--- | :--- |
| D1 | [解析器抽象](d1-parser-abstraction.md) | BaseParser、注册表 |
| D2 | [各格式解析器](d2-format-parsers.md) | PDF/DOCX/TXT |
| D3 | [清洗](d3-cleaning.md) | 去噪、归一化、去重 |
| D4 | [切分](d4-chunking.md) | 固定长度、chunk_hash |
| D5 | [单元测试](d5-unit-tests.md) | fixtures、边界用例 |
| D6 | [验收标准](d6-acceptance.md) | 阶段 D 达成标志 |

## 阶段 E · Embedding + Qdrant 入库（3-4 天）

| 任务 | 文件 | 说明 |
| :--- | :--- | :--- |
| E1 | [Embedding 客户端](e1-embedding-client.md) | OpenAI、批量/重试/token 统计 |
| E2 | [Qdrant 写入](e2-qdrant-write.md) | payload、point id、批量 upsert |
| E3 | [MySQL 元数据写入](e3-mysql-metadata.md) | chunks 批量写、顺序约定 |
| E4 | [一致性保障](e4-consistency.md) | 幂等、对账脚本 |
| E5 | [验收标准](e5-acceptance.md) | 阶段 E 达成标志 |

## 阶段 F · Celery 任务流水线（4-5 天）

| 任务 | 文件 | 说明 |
| :--- | :--- | :--- |
| F1 | [Celery 基础](f1-celery-base.md) | app 配置、任务基类、Flower |
| F2 | [流水线编排](f2-pipeline.md) | chain、状态机、重试、幂等 |
| F3 | [触发入口](f3-trigger.md) | 上传投递、reprocess、取消 |
| F4 | [验收标准](f4-acceptance.md) | 阶段 F 达成标志 |

## 阶段 G · 任务 / Chunk / 检索测试 API（3-4 天）

| 任务 | 文件 | 说明 |
| :--- | :--- | :--- |
| G1 | [任务接口](g1-job-api.md) | 列表/详情/步骤/重试/取消 |
| G2 | [检索测试接口](g2-search-test.md) | 强制租户/版本过滤 |
| G3 | [统计接口](g3-stats.md) | 文档/chunk/成功率 |
| G4 | [验收标准](g4-acceptance.md) | 阶段 G 达成标志 |

## 阶段 H · 前端管理界面（5-6 天）

| 任务 | 文件 | 说明 |
| :--- | :--- | :--- |
| H1 | [前端工程初始化](h1-frontend-init.md) | Vite + Ant Design Pro、axios |
| H2 | [文档管理页](h2-document-page.md) | 列表/上传/详情/chunk 预览 |
| H3 | [任务看板](h3-job-board.md) | 列表/步骤时间线/轮询 |
| H4 | [检索测试页](h4-search-page.md) | query/top_k/结果 |
| H5 | [设置页](h5-settings-page.md) | 默认配置只读 |
| H6 | [验收标准](h6-acceptance.md) | 阶段 H 达成标志 |

## 阶段 I · 测试、联调、验收（3-4 天）

| 任务 | 文件 | 说明 |
| :--- | :--- | :--- |
| I1 | [自动化测试](i1-automated-tests.md) | 单测、集成测试、覆盖率 |
| I2 | [联调](i2-integration.md) | 前后端对接、大文件、并发 |
| I3 | [部署与文档](i3-deploy-docs.md) | compose 生产示例、README/API/Runbook |
| I4 | [MVP 验收清单](i4-mvp-acceptance.md) | 最终验收 |
