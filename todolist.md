# MVP Todolist — RAG Ingestion Management System

> 对应 plan.md 第十一节 MVP 建议：4-6 周跑通最小闭环  
> 技术栈：FastAPI + SQLAlchemy + Pydantic / Celery + Redis / MySQL / Qdrant / MinIO / React + Ant Design Pro

---

## 0. 总览

| 阶段 | 模块 | 预估工时 | 依赖 |
| :--- | :--- | :--- | :--- |
| A | 项目脚手架与基础设施 | 3-4 天 | - |
| B | 数据模型与存储层 | 2-3 天 | A |
| C | 文档上传与元数据 API | 3-4 天 | B |
| D | 解析、清洗、切分模块 | 4-5 天 | B |
| E | Embedding + Qdrant 入库 | 3-4 天 | D |
| F | Celery 任务流水线 | 4-5 天 | C/D/E |
| G | 任务/Chunk/检索测试 API | 3-4 天 | F |
| H | 前端管理界面 | 5-6 天 | C/G |
| I | 测试、联调、验收 | 3-4 天 | 全部 |

**关键路径**：A → B → D → E → F → G → I（H 可与 F/G 并行）

---

## A. 项目脚手架与基础设施（3-4 天）

### A1. 仓库与工程结构
- [ ] 初始化 monorepo：`backend/`、`frontend/`、`deploy/`、`docs/`
- [ ] 后端 `requirements.txt`+ Poetry 锁定依赖
- [ ] 目录分层：`api/`、`core/`、`models/`、`schemas/`、`services/`、`workers/`、`parsers/`、`chunkers/`、`clients/`、`utils/`
- [ ] 统一日志配置（loguru，JSON 输出）
- [ ] 统一配置管理（pydantic-settings，`.env` + `config.py`）
- [ ] `.gitignore`、`.editorconfig`、`pre-commit`（ruff + black + mypy）

### A2. 本地开发环境
- [ ] `docker-compose.yml`：MySQL 8、Redis 7、Qdrant、MinIO、backend、worker、flower
- [ ] MySQL 初始化脚本（建库、字符集 utf8mb4）
- [ ] MinIO 初始化 bucket（`raw-docs`、`parsed-text`）
- [ ] Qdrant collection 初始化脚本（dimension 按默认 embedding 模型定，distance=COSINE）
- [ ] `.env.example` 覆盖全部配置项并注释

### A3. FastAPI 骨架
- [x] `main.py` 启动、CORS、路由注册、异常处理器
- [x] `/healthz`、`/readyz` 健康检查
- [x] OpenAPI 自动文档（`/docs`）确认可访问
- [x] 统一响应结构（`code/message/data`）与分页规范
- [x] 全局依赖：DB session、当前用户（MVP 可先固定租户/用户）

### A4. 验收标准
- [ ] `docker compose up` 一键拉起全部依赖
- [ ] 访问 `/docs` 与 `/healthz` 正常
- [ ] CI 能跑 lint + 单测（GitHub Actions 最小流水线）

---

## B. 数据模型与存储层（2-3 天）

### B1. 数据库表（MVP 子集）
> 只建 MVP 必需表（9 张）；plan.md 第四节标注「延后」的 6 张（chunking_strategies / parsers / permissions / audit_logs / evaluation_runs / quality_checks）不建。版本/权限相关字段先留位。表结构定义见 `docs/db-schema.md`。

- [x] `tenants`（MVP 预置一条默认租户）
- [x] `users`（MVP 预置默认管理员）
- [x] `datasources`（MVP 只实现 `local` 类型）
- [x] `documents`（含 `tenant_id`、`status`、`current_version`）
- [x] `document_versions`（含 `content_hash`、`parse_status`、`chunk_count`、`is_latest`、`is_deleted`、`file_path`）
- [x] `chunks`（含 `doc_version_id`、`chunk_index`、`text`、`token_count`、`chunk_hash`、`qdrant_point_id`、`metadata`）
- [x] `ingestion_jobs`（含 `job_type`、`status`、`priority`、`celery_task_id`、时间戳、`error_message`）
- [x] `job_steps`（含 `step_name`、`step_order`、`status`、`retry_count`、`input/output`、时间戳）
- [x] `embedding_models`（预置 OpenAI `text-embedding-3-small` 一条默认配置）

### B2. ORM 与迁移
- [x] SQLAlchemy 2.0 模型定义（UUID 主键 `CHAR(36)`、时间戳 mixin、JSON 列用 MySQL `JSON`）
- [x] Alembic 初始化，生成首版迁移
- [x] `created_at/updated_at` 自动维护
- [x] 关键索引：`documents(tenant_id, status)`、`document_versions UNIQUE(doc_id, content_hash)`、`chunks(doc_version_id, chunk_index)`、`chunks(doc_id)`、`ingestion_jobs(tenant_id, status)`、`job_steps(job_id, step_order)`（FK 列 InnoDB 自动建索引，无需重复建）
- [x] 种子脚本：默认租户、用户、embedding 模型配置

### B3. 存储层封装
- [x] MinIO 客户端封装：`upload_file`、`download_file`、`generate_presigned_url`、`delete_object`
- [x] Qdrant 客户端封装：`ensure_collection`、`upsert_points`、`delete_by_filter`、`search`
- [x] 统一 `StorageService`，便于替换实现

### B4. 验收标准
- [x] `alembic upgrade head` 一键建表
- [x] 种子脚本可重复执行（幂等）
- [x] 单测覆盖 Storage 封装（用 MinIO/Qdrant 容器或 mock）

---

## C. 文档上传与元数据 API（3-4 天）

### C1. 上传接口
- [x] `POST /documents/upload`：multipart 上传，校验文件类型（pdf/docx/txt）与大小上限
- [x] 计算 `content_hash`（SHA256）
- [x] 上传原始文件到 MinIO（`raw-docs/{tenant_id}/{doc_id}/{version}/{filename}`）
- [x] 创建 `documents` + `document_versions`（`version=1`、`is_latest=true`、`status=processing`）
- [x] 创建 `ingestion_jobs`（`job_type=full`、`status=pending`）并投递 Celery 任务
- [x] 幂等：相同 `content_hash` 已存在时，返回已有 doc（或提示跳过）

### C2. 文档查询接口
- [x] `GET /documents`：分页、按 `tenant_id`/`status`/`file_type` 过滤、关键字搜索标题
- [x] `GET /documents/{id}`：返回文档详情 + 最新版本信息
- [x] `GET /documents/{id}/chunks`：分页返回 chunk 列表（含 `text`、`chunk_index`、`token_count`、`page`）
- [x] `DELETE /documents/{id}`：MVP 做软删除（`documents.status=deleted`，异步清理可延后）

### C3. 数据源接口（MVP 最小）
- [x] `GET /datasources`、`POST /datasources`（仅 `type=local`，占位）
- [x] 上传时自动关联默认 datasource（或允许指定 `datasource_id`）

### C4. 验收标准
- [x] 上传 PDF/DOCX/TXT 均成功落库 + 落 MinIO
- [x] 上传后能查到 `documents`、`document_versions`、`ingestion_jobs` 记录
- [x] 重复上传相同文件触发幂等逻辑
- [x] 接口有 Pydantic schema 校验与错误码

---

## D. 解析、清洗、切分模块（4-5 天）

### D1. 解析器抽象
- [x] 定义 `BaseParser` 接口：`parse(file_path) -> ParsedDocument{text, blocks, metadata}`
- [x] 解析器注册表：按 `file_type` 分派

### D2. 各格式解析器
- [x] **PDF**：`pymupdf`（优先）或 `pdfplumber`，提取文本 + 页码 + 基本元数据
- [x] **DOCX**：`python-docx`，提取段落 + 表格（表格转 markdown/文本）
- [x] **TXT**：直接读取（编码探测，`chardet`）
- [x] 解析结果统一落 MinIO（`parsed-text/{doc_version_id}.json`）
- [x] 解析失败写入 `document_versions.parse_status=failed` + `job_steps.error_message`

### D3. 清洗
- [x] 去噪：多余空白、页眉页脚重复行、控制字符
- [x] 统一换行、去重连续重复段落
- [x] 可选：简单语言检测（避免乱码）
- [x] 清洗结果保留块级结构（含页码、段落类型）

### D4. 切分
- [ ] 定义 `BaseChunker` 接口：`chunk(parsed_doc, config) -> List[Chunk]`
- [ ] 固定长度切分器：按 token（`tiktoken`）切分，支持 `chunk_size`、`overlap`
- [ ] 每个 chunk 计算 `chunk_hash`（SHA256 of text）
- [ ] 每个 chunk 携带 `chunk_index`、`page`（若可得）、`metadata`
- [ ] 提供默认切分配置（如 `chunk_size=512, overlap=50`）

### D5. 单元测试
- [ ] 三种格式各准备样例文件（`tests/fixtures/`）
- [ ] 解析 → 清洗 → 切分 端到端单测
- [ ] 边界用例：空文件、加密 PDF、超大文件、超长单段

### D6. 验收标准
- [ ] 三种格式样例均能产出非空 chunk 列表
- [ ] chunk 的 `token_count` 与 `chunk_size` 配置一致（±overlap）
- [ ] 解析失败可正确落库并可见错误信息

---

## E. Embedding + Qdrant 入库（3-4 天）

### E1. Embedding 客户端
- [ ] `BaseEmbedder` 接口：`embed_batch(texts) -> List[List[float]]`
- [ ] OpenAI 实现：`text-embedding-3-small`，支持批量（如每批 64 条）
- [ ] 限流与重试：指数退避、429/5xx 重试
- [ ] Token 统计：记录每批 token 数，写入 `job_steps.output`
- [ ] 配置从 `embedding_models` 表读取（含 `dimension`）

### E2. Qdrant 写入
- [ ] Collection 初始化（dimension 对齐模型，distance=COSINE）
- [ ] Payload 字段：`tenant_id`、`doc_id`、`doc_version_id`、`version`、`is_latest`、`is_deleted`、`access_level`、`chunk_index`、`page`、`chunk_hash`、`text`（可选）
- [ ] Point ID 生成策略：UUID 或 `doc_version_id + chunk_index` 的确定性 ID（便于幂等 upsert）
- [ ] 批量 upsert，失败重试
- [ ] 回写 `chunks.qdrant_point_id`

### E3. MySQL 元数据写入
- [ ] 批量写入 `chunks` 表（含 `token_count`、`chunk_hash`、`metadata`）
- [ ] 更新 `document_versions.chunk_count`、`embedding_model`
- [ ] 顺序约定：**先写 MySQL，再写 Qdrant，最后回写 point_id**（失败可重试对账）

### E4. 一致性保障
- [ ] 幂等：相同 `doc_version_id` 重复处理时先按 filter 删除旧 points
- [ ] 对账脚本（MVP 简易版）：扫描 `chunks` 缺失 `qdrant_point_id` 的记录并重试

### E5. 验收标准
- [ ] 样例文档全流程后，Qdrant 中 points 数与 `chunks` 表一致
- [ ] payload 字段完整，`is_latest=true`
- [ ] 相同文档重复处理不产生重复 points

---

## F. Celery 任务流水线（4-5 天）

### F1. Celery 基础
- [ ] Celery app 配置：Broker=Redis，Result backend=Redis
- [ ] 队列划分：`parse`、`embed`、`default`（MVP 可先单队列，但保留扩展点）
- [ ] Flower 接入（本地开发可视）
- [ ] 任务基类：统一 job_step 记录、异常捕获、状态更新

### F2. 流水线编排
- [ ] Chain：`download → parse → clean → chunk → embed → upsert → index(可选) → finalize`
- [ ] 每一步：更新 `job_steps.status/started_at/finished_at/output/error_message`
- [ ] 任务整体状态机：`pending → running → success / failed`
- [ ] 失败重试：每步 `max_retries=3`，指数退避
- [ ] 幂等：以 `doc_version_id` 为幂等键，避免重复处理

### F3. 触发入口
- [ ] 上传接口投递任务
- [ ] `POST /documents/{id}/reprocess`：创建新 job 并投递
- [ ] 任务取消（MVP 可选：标记 cancelled，worker 检查中断）

### F4. 验收标准
- [ ] 上传后任务自动流转至 success
- [ ] `job_steps` 每步有耗时与 output
- [ ] 人为制造解析失败，任务状态为 failed 且 error_message 可读
- [ ] 重试机制生效（可 mock 外部依赖失败验证）

---

## G. 任务 / Chunk / 检索测试 API（3-4 天）

### G1. 任务接口
- [ ] `GET /jobs`：分页、按 status/job_type 过滤
- [ ] `GET /jobs/{id}`：任务详情
- [ ] `GET /jobs/{id}/steps`：步骤列表（含耗时、状态、错误）
- [ ] `POST /jobs/{id}/retry`：失败任务重投
- [ ] `POST /jobs/{id}/cancel`：标记取消

### G2. 检索测试接口
- [ ] `POST /search/test`：入参 `{query, top_k, tenant_id, filters}` 
- [ ] 调用 embedding 生成 query 向量 → Qdrant search
- [ ] 返回：`score`、`text`、`doc_id`、`version`、`page`、`metadata`
- [ ] 强制 `tenant_id` 过滤 + `is_latest=true` + `is_deleted=false`
- [ ] 返回耗时（embedding / search 分项）

### G3. 统计接口（MVP 最小）
- [ ] `GET /stats`：文档数、chunk 数、任务成功率、今日处理量

### G4. 验收标准
- [ ] 检索测试能返回相关 chunk，score 合理
- [ ] 跨租户数据不可见
- [ ] 任务列表与步骤可视化数据完整

---

## H. 前端管理界面（5-6 天）

### H1. 工程初始化
- [ ] React + Vite + TypeScript + Ant Design Pro 初始化
- [ ] 路由、布局（侧边栏：文档 / 任务 / 检索测试 / 设置）
- [ ] API 客户端封装（axios + 拦截器 + 统一错误提示）
- [ ] 环境变量配置（`VITE_API_BASE_URL`）

### H2. 文档管理页
- [ ] 文档列表：分页、筛选（状态/类型）、标题搜索
- [ ] 上传组件：拖拽上传、进度条、类型校验
- [ ] 文档详情抽屉/页：基础信息、版本信息、当前状态
- [ ] Chunk 预览：列表 + 分页 + 高亮 `chunk_index`/`page`
- [ ] 重新处理按钮、软删除按钮

### H3. 任务看板
- [ ] 任务列表：状态标签、耗时、创建时间、筛选
- [ ] 任务详情：步骤时间线（parse/clean/chunk/embed/upsert），每步状态与错误
- [ ] 重试 / 取消操作
- [ ] 简易轮询刷新（MVP 不做 WebSocket）

### H4. 检索测试页
- [ ] 输入 query、top_k、可选过滤条件
- [ ] 结果列表：score、文本片段、来源文档、页码
- [ ] 展示 embedding/search 耗时

### H5. 设置页（MVP 最小）
- [ ] 查看默认 Embedding 模型配置（只读即可）
- [ ] 查看切分参数（只读或简单可编辑）

### H6. 验收标准
- [ ] 上传 → 看任务进度 → 看 chunk → 检索测试 全链路可在 UI 完成
- [ ] 错误提示友好（上传失败、任务失败、检索无结果）
- [ ] 响应式基本可用（桌面优先）

---

## I. 测试、联调、验收（3-4 天）

### I1. 自动化测试
- [ ] 后端单测：parsers、chunkers、embedder(mock)、API
- [ ] 集成测试：上传 → 任务 → 入库 → 检索（用 docker-compose 依赖）
- [ ] 覆盖率目标：核心模块 ≥ 70%
- [ ] CI 跑通 lint + test

### I2. 联调
- [ ] 前端对接全部 API，修复字段/分页/错误码不一致
- [ ] 大文件（如 50MB PDF）性能与超时验证
- [ ] 并发上传 10 个文档，验证队列与幂等

### I3. 部署与文档
- [ ] `deploy/` 提供 compose 生产示例（含资源限制）
- [ ] `README.md`：本地启动、环境变量、常见问题
- [ ] `docs/api.md`：接口清单与示例（可由 OpenAPI 导出）
- [ ] `docs/runbook.md`：任务失败排查、Qdrant 重建、MinIO 清理

### I4. MVP 验收清单
- [ ] 上传 PDF/DOCX/TXT → 自动解析 → 切分 → 向量化 → 入库
- [ ] 文档列表、任务状态、Chunk 预览、检索测试四类页面可用
- [ ] 相同文件重复上传不重复处理（幂等）
- [ ] 任务失败可见错误并支持重试
- [ ] 检索结果按租户隔离、只返回 `is_latest` 数据
- [ ] 全链路可在 docker-compose 环境一键复现

---

## 附：MVP 明确不做（防止范围蔓延）

- ❌ 版本回滚、增量更新、软删除后的异步清理
- ❌ 多租户权限体系、ACL 同步、审计日志
- ❌ 定时同步、Webhook、S3/SharePoint/Confluence 等数据源
- ❌ 语义切分、父子块、OCR、表格深度解析
- ❌ OpenSearch 全文索引（MVP 仅 Qdrant 向量检索）
- ❌ 质量评估、A/B、成本看板
- ❌ Temporal（MVP 用 Celery，后续迁移）
- ❌ WebSocket 实时进度（用轮询）

---

## 附：建议里程碑

| 里程碑 | 时间点 | 达成标志 |
| :--- | :--- | :--- |
| M1 环境就绪 | 第 1 周末 | docker-compose 全服务可启动，表结构就绪 |
| M2 后端闭环 | 第 3 周末 | 上传→解析→切分→embedding→Qdrant 全链路 API 可用 |
| M3 前端可用 | 第 4-5 周 | 四类页面可操作全流程 |
| M4 MVP 验收 | 第 6 周 | 验收清单全绿，文档齐备 |