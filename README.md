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

## 本地启动（Windows PowerShell 示例）

### 1. 基础设施

```powershell
cd deploy
docker compose up -d          # MySQL 3306 / Redis 6379 / Qdrant 6333 / MinIO 9000-9001
```

### 2. 后端

```powershell
cd backend
Copy-Item .env.example .env   # 填 OPENAI__API_KEY 等真实值
python -m venv env; .\env\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
.\env\Scripts\python.exe scripts\seed.py
.\env\Scripts\python.exe scripts\init_qdrant.py
.\env\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# 另开一个终端
.\env\Scripts\celery.exe -A app.workers.celery_app worker -Q parse,embed,default -l info --pool solo
```

### 3. 前端

```powershell
cd frontend
pnpm install
pnpm dev      # http://localhost:5173（文档 / 任务 / 检索测试 / 设置）
```

### 生产部署示例

`deploy/docker-compose.prod.yml`（含资源限制、多 worker 副本、手工启动步骤注释）。

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
- **上传返回 413**：超过 50MB；415：类型不符（仅 pdf/docx/txt）。
- **任务一直 pending**：Celery worker 未启动；`celery inspect ping` 无响应说明 broker/队列问题。
- **Windows worker 建议 `--pool solo`**：prefork 在 Windows 不可用。
- **搜索 0 命中但任务 succeeded**：确认检索租户与上传租户一致（MVP 认证 stub 固定租户）；Qdrant 点数用 runbook 的对账脚本检查。
- **前端 CORS 报错**：`APP__CORS_ORIGINS` 需含 `http://localhost:5173`。

## 质量与 CI

- 后端门禁：`pytest`（247 单测 + 2 真栈集成，见 `tests/test_i1_integration.py`）、`ruff`、`black`、`mypy`。
- CI：`.github/workflows/ci.yml`（lint + test + 覆盖率 ≥70%，前端 typecheck + build）。
