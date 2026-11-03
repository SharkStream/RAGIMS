# RAGIMS

RAG Ingestion Management System — 文档摄取与向量化管理系统。上传 pdf/docx/txt → 解析/清洗/切分 → 向量化 → 入库 Qdrant，配套任务看板、检索测试与设置页面。

## 架构（MVP 已实现）

```
前端 React+Vite (:5173)
   │  axios {code,message,data}
   ▼
FastAPI 后端 (:8000, /api)
   │ 上传幂等(hash) → Celery 任务派发
   ▼
Redis 队列 (parse/embed/default)
   │
   ▼ Celery worker 七步流水线
parse(PyMuPDF/docx) → clean → chunk(tiktoken 512/50)
   → persist_chunks(MySQL) → embed(OpenAI 兼容)
   → upsert(Qdrant) → write_back
   ▼
MySQL 8 元数据 · MinIO 原始/解析文本 · Qdrant 向量
```

- 后端：FastAPI + SQLAlchemy 2.0 + Celery 5 + MySQL 8 + MinIO + Qdrant（详见 [backend/README.md](./backend/README.md)）
- 前端：React 18 + Vite 5 + Ant Design Pro（详见 [frontend/README.md](./frontend/README.md)）
- 任务状态机与 API 清单：[docs/api.md](./docs/api.md)；运维：[docs/runbook.md](./docs/runbook.md)

## 快速开始：克隆后把系统跑起来（约 10 分钟）

> 以下命令在 **Windows PowerShell** 验证过；Linux/macOS 差异见每步末尾的提示。
> 项目根目录统一记为 `<repo>`（即克隆下来的 `RAGIMS/`）。

### 0. 前置要求

| 工具 | 版本 | 检查命令 |
| :-- | :-- | :-- |
| Docker Desktop | 任意近期版本（含 compose v2） | `docker compose version` |
| Python | **≥3.11 且 <3.14**（3.13 实测通过） | `python --version` |
| Node.js | ≥20 | `node -v` |
| pnpm | ≥9（`npm i -g pnpm`） | `pnpm -v` |
| 一个 OpenAI 兼容的 Embedding API Key | — | 无则系统无法完成向量化 |

### 1. 启动基础设施（MySQL / Redis / Qdrant / MinIO）

```powershell
cd <repo>\deploy
docker compose up -d
docker compose ps        # 等四个服务全部 healthy（约 30 秒）
```

<details><summary>Linux/macOS：完全相同，只是路径分隔符不同</summary>

```bash
cd <repo>/deploy && docker compose up -d && docker compose ps
```
</details>

这一步会创建：MySQL 8（`ragims` 库 + utf8mb4）、Redis 7（broker）、Qdrant、MinIO（含 `raw-docs`/`parsed-text` 两个桶，由 `minio-init` 一次性任务建好）。

### 2. 配置后端环境变量

```powershell
cd <repo>\backend
Copy-Item .env.example .env
notepad .env             # 至少改下面这一项：
```

**必改**：`OPENAI__API_KEY`（你的 key）。其余默认值已对准第 1 步的 compose 端口/账号（MySQL root 密码 `ragims`、MinIO `minioadmin`），可直接用。
**注意**：`OPENAI__EMBEDDING_DIMENSION`（默认 1536）必须与你使用的模型实际输出维度一致，换模型时同步改；`OPENAI__BASE_URL` 换成你的 OpenAI 兼容网关地址（如非官方 API）。

### 3. 安装后端依赖 + 初始化数据

```powershell
python -m venv env
.\env\Scripts\Activate.ps1          # 激活虚拟环境（每次开新终端都要先激活）
pip install -r requirements.txt
alembic upgrade head                # 建 9 张表
python scripts\seed.py              # 种子数据：默认租户/用户/数据源/Embedding 模型
python scripts\init_qdrant.py       # 创建 Qdrant collection（维度取自 .env）
```

- Linux/macOS：`python3 -m venv env && source env/bin/activate`，其余命令把 `\` 换 `/`。

### 4. 启动后端 API 与任务 worker（两个终端）

```powershell
# 终端 A —— API 服务
cd <repo>\backend; .\env\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 B —— Celery worker（不上传文件时可以不启动，但任务会一直 pending）
cd <repo>\backend; .\env\Scripts\Activate.ps1
.\env\Scripts\celery.exe -A app.workers.celery_app worker -Q parse,embed,default -l info --pool solo
```

- `--pool solo` 是 **Windows 必须**的（prefork 在 Windows 不可用）；Linux/macOS 去掉它即可。

### 5. 启动前端

```powershell
cd <repo>\frontend
pnpm install
pnpm dev                # http://localhost:5173
```

### 6. 验证系统已经跑通

1. 浏览器打开 `http://localhost:5173` —— 应看到文档列表页（空列表正常）。
2. 拖入一个 pdf/docx/txt 上传 —— 任务看板出现新 job，约几十秒后变 **succeeded**。
3. 「检索测试」页用文档里的原句搜索 —— 能返回带分数的命中。
4. 也可以直接验证 API：`http://localhost:8000/docs`（Swagger UI）。

**如果卡住**，按顺序查：四个容器是否 healthy → `OPENAI__API_KEY` 是否已填 → 终端 B 的 worker 是否在跑 → 更多排查见 [docs/runbook.md](./docs/runbook.md)。

### 生产部署示例

`deploy/docker-compose.prod.yml`（含资源限制、多 worker 副本、手工启动步骤注释，默认不自动运行）。

## 环境变量

全部经 `.env` 注入（`__` 为嵌套分隔符，完整键见 `backend/.env.example`）：

| 键 | 说明 | 默认 |
| :-- | :-- | :-- |
| `OPENAI__API_KEY` | embedding API key（**必填**，缺失启动报错） | — |
| `OPENAI__BASE_URL` | OpenAI 兼容网关 | api.openai.com/v1 |
| `OPENAI__EMBEDDING_MODEL` / `_DIMENSION` | 模型与维度（须与 Qdrant collection 一致） | text-embedding-3-small / 1536 |
| `MYSQL__HOST/PORT/USER/PASSWORD/DATABASE` | 元数据库 | localhost/3306/root/ragims |
| `REDIS__HOST/PORT` | Celery broker | localhost/6379 |
| `QDRANT__HOST/PORT` | 向量库 | localhost/6333 |
| `MINIO__ENDPOINT/ACCESS_KEY/SECRET_KEY` | 对象存储 | localhost:9000/minioadmin |
| `APP__CHUNK_SIZE` / `APP__CHUNK_OVERLAP` | 切分参数 | 512 / 50 |
| `APP__UPLOAD_MAX_MB` | 上传上限 | 50 |
| `VITE_API_BASE_URL`（前端） | API 前缀 | http://127.0.0.1:8000/api |

## 常见问题（FAQ）

- **启动即 ValidationError**：`.env` 缺 `OPENAI__API_KEY`；或 `OPENAI__EMBEDDING_DIMENSION` 与既有 collection 维度不一致（重建 collection，见 runbook）。
- **上传返回 413**：超过 50MB；415：类型不符（支持 pdf/docx/txt/md）。
- **任务一直 pending**：Celery worker 未启动；`celery inspect ping` 无响应说明 broker/队列问题。
- **Windows worker 建议 `--pool solo`**：prefork 在 Windows 不可用。
- **搜索 0 命中但任务 succeeded**：确认检索租户与上传租户一致（MVP 认证 stub 固定租户）；Qdrant 点数用 runbook 的对账脚本检查。
- **前端 CORS 报错**：`APP__CORS_ORIGINS` 需含 `http://localhost:5173`。

## 质量与 CI

- 后端门禁：`pytest`（247 单测 + 2 真栈集成，见 `tests/test_i1_integration.py`）、`ruff`、`black`、`mypy`。
- CI：`.github/workflows/ci.yml`（lint + test + 覆盖率 ≥70%，前端 typecheck + build）。
