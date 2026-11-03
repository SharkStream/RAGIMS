# A2 · 本地开发环境

> **阶段**：A 项目脚手架与基础设施（3-4 天）　**依赖**：A1　**工时**：约 1 天

## 目标

用 docker-compose 一键拉起全部基础设施（MySQL、Redis、Qdrant、MinIO、backend、worker、flower），并完成各存储的初始化脚本。

## 实施步骤

### 1. `deploy/docker-compose.yml`
- 服务：`mysql:8`、`redis:7`、`qdrant`、`minio`、`backend`、`worker`（Celery）、`flower`。
- backend/worker 挂载 `backend/` 卷，便于热加载。
- 健康检查（healthcheck）：MySQL `mysqladmin ping`、Redis `redis-cli ping`、Qdrant `/healthz`、MinIO `/minio/health/live`。

### 2. MySQL 初始化脚本
- 文件：`deploy/mysql/init.sql`
- 建库 `ragims`，字符集 `utf8mb4`、排序规则 `utf8mb4_unicode_ci`。

### 3. MinIO 初始化 bucket
- 文件：`deploy/minio/init.sh`（或用 compose 的 `minio/mc` 初始化容器）
- 建两个 bucket：`raw-docs`（原始文件）、`parsed-text`（解析后文本）。

### 4. Qdrant collection 初始化脚本
- 文件：`backend/app/clients/qdrant.py` 的 `ensure_collection()`（B3 复用）。
- dimension 按默认 embedding 模型定（OpenAI `text-embedding-3-small` = **1536**），`distance=COSINE`。
- 提供 `backend/scripts/init_qdrant.py` 单独执行初始化。

### 5. `.env.example`
- 覆盖全部配置项并逐条注释：MySQL DSN、Redis URL、Qdrant URL、MinIO 地址与密钥、OpenAI API Key、默认 embedding 模型与 dimension。

## 验收标准

- [ ] `docker compose up` 一键拉起全部依赖，各服务健康。
- [ ] MySQL 库 `ragims` 建好，字符集为 `utf8mb4`。
- [ ] MinIO 两个 bucket 就位。
- [ ] Qdrant collection 创建成功，dimension=1536、COSINE。
- [ ] `.env.example` 覆盖所有 `Settings` 配置项。

## 关联任务

- 依赖 [A1 仓库与工程结构](a1-repo-structure.md)；被 [A3 FastAPI 骨架](a3-fastapi-skeleton.md) 与 [B2 ORM 与迁移](b2-orm-migration.md) 使用。
