# RAGIMS Backend

RAG Ingestion Management System 后端：文档上传 → 解析/清洗/切分 → 向量化 → Qdrant 入库的完整摄取流水线，配套任务 / 检索测试 / 统计 API。

## 技术栈

| 层 | 技术 | 说明 |
| :-- | :-- | :-- |
| Web 框架 | **FastAPI** + Uvicorn | 统一响应信封 `{code, message, data}`，全局异常处理 |
| ORM / 迁移 | **SQLAlchemy 2.0** + Alembic | 元数据库 **MySQL 8**（utf8mb4，UUID 主键 `CHAR(36)`） |
| 数据校验 | **Pydantic v2** + pydantic-settings | `.env` 配置用 `__` 作嵌套分隔符 |
| 任务队列 | **Celery 5** + Redis broker | 三队列（parse / embed / default），七步流水线 + 双层重试 |
| 向量库 | **Qdrant** | 余弦相似度，payload 强制租户/版本过滤 |
| 对象存储 | **MinIO** | 原始文件 `raw-docs` / 解析文本 `parsed-text` |
| Embedding | **OpenAI 兼容 API** | `text-embedding-3-small`（1536 维，可换本地网关） |
| 解析/切分 | PyMuPDF / python-docx / tiktoken | pdf/docx/txt 解析 + 固定 token 切分 |
| 监控 | Flower | Celery 任务监控 UI（:5555） |
| 质量 | ruff / black / mypy / pytest | 全量门禁（当前 243 passed，70 文件 mypy 零错误） |

Python 版本要求：**≥ 3.11，< 3.14**。

## 目录结构

```
backend/
├── app/
│   ├── api/            # 路由：documents / jobs / search / stats / datasources / health
│   ├── services/       # 业务：上传、流水线、检索、统计、对账……
│   ├── workers/        # Celery：celery_app / base(任务基类) / pipeline(七步编排)
│   ├── models/         # 9 张表 ORM（documents / chunks / ingestion_jobs / job_steps …）
│   ├── schemas/        # Pydantic 请求/响应模型
│   ├── clients/        # Embedder / Qdrant 封装
│   └── core/           # 配置、DB、日志、异常、依赖
├── alembic/            # 迁移脚本
├── scripts/            # seed.py（初始化种子数据）/ init_qdrant.py / reconcile.py
├── tests/              # 离线 pytest（不依赖外部服务）
├── deploy -> ../deploy # docker compose（MySQL/Redis/Qdrant/MinIO/backend/worker/flower）
└── requirements.txt    # 依赖（也可用 Poetry：poetry install）
```

## 快速启动

### 1. 基础设施（Docker Compose）

```powershell
cd ../deploy
docker compose up -d        # MySQL 3306 / Redis 6379 / Qdrant 6333 / MinIO 9000-9001
```

### 2. 配置环境变量

```powershell
cd ../backend
Copy-Item .env.example .env
# 编辑 .env：至少填 OPENAI__API_KEY（缺失会在启动时报 ValidationError），
# 并核对 MySQL/Redis/Qdrant/MinIO 连接参数
```

### 3. 安装依赖（建议虚拟环境）

```powershell
python -m venv env
.\env\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. 初始化数据库与向量库

```powershell
alembic upgrade head                       # 建 9 张表
.\env\Scripts\python.exe scripts\seed.py        # 种子租户/用户/模型
.\env\Scripts\python.exe scripts\init_qdrant.py # 创建 documents collection
```

### 5. 启动 API 服务

```powershell
.\env\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Swagger: http://127.0.0.1:8000/docs
```

### 6. 启动 Celery Worker（摄取流水线）

```powershell
.\env\Scripts\celery.exe -A app.workers.celery_app worker -Q parse,embed,default -l info --pool solo
```

> `--pool solo` 适合 Windows 本机开发；Linux 可去掉并用默认 prefork。
> Flower 监控：`celery -A app.workers.celery_app flower --port=5555`（或 compose 里的 `flower` 服务）。

## API 概览（前缀 `/api`）

| 方法 | 路径 | 说明 |
| :-- | :-- | :-- |
| POST | `/documents/upload` | 上传 pdf/docx/txt（内容哈希幂等，自动投递流水线） |
| GET | `/documents` / `/documents/{id}` / `/{id}/chunks` | 列表 / 详情 / Chunk 预览 |
| DELETE | `/documents/{id}` | 软删除 |
| POST | `/documents/{id}/reprocess` | 重处理（新建 reprocess job） |
| GET | `/jobs` / `/jobs/{id}` / `/jobs/{id}/steps` | 任务列表 / 详情 / 步骤（含耗时与 output） |
| POST | `/jobs/{id}/retry` / `/jobs/{id}/cancel` | 失败重投 / 协作取消 |
| POST | `/search/test` | 检索测试（租户隔离硬过滤，返回分项耗时） |
| GET | `/stats` | 文档数 / chunk 数 / 任务成功率 / 今日处理量 |

## 测试与质量门禁

```powershell
.\env\Scripts\python.exe -m pytest tests -q -p no:cacheprovider   # 离线全量（243 passed）
.\env\Scripts\ruff.exe check app tests scripts
.\env\Scripts\black.exe --check app tests
.\env\Scripts\mypy.exe app scripts/seed.py --cache-dir $env:TEMP\mypy_cache_ragims
```

## 运维脚本

- `scripts/reconcile.py` — MySQL 与 Qdrant 对账（修复丢点/孤儿点）
- `scripts/init_qdrant.py` — 初始化/校验向量 collection
- `scripts/seed.py` — 默认租户 / 用户 / embedding model 种子数据
