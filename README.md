# RAGIMS

RAG Ingestion Management System — 文档摄取与向量化管理系统。上传 pdf/docx/txt → 解析/清洗/切分 → 向量化 → 入库 Qdrant，配套任务看板、检索测试、版本管理、多租户权限（登录/角色/密级/审计）与设置页面。

**当前进度：plan.md 前三个阶段全部完成 ✅**（MVP1 摄取主链路 → MVP2 版本与增量 → MVP3 权限与多租户）；下一阶段：阶段 4 · 质量与评估。

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

## 里程碑（阶段 A–K 全部完成）

| 阶段 | 代号 | 主题 | 核心成果 | 任务卡 |
| :-: | :-: | :-- | :-- | :-: |
| MVP1 | A–I | 摄取主链路 | 9 张表 + 异步 7 步流水线 + 上传幂等 + API 全家桶 + React 四页 + 门禁体系 | [docs/mvp1](./docs/mvp1/README.md) |
| MVP2 | J1–J6 | 版本与增量 | 增量上传（内容变→新版本，同→幂等）/ 版本 API / 元数据零重嵌入 PATCH / 历史回滚（MySQL 指针 + Qdrant payload 原子翻转）/ 版本级回收 / 前端 3-Tab 抽屉 | [docs/mvp2](./docs/mvp2/README.md) |
| MVP3 | K1–K6 | 权限与多租户 | 审计日志（7 类写路径 + 查询 API）/ 真实登录（HMAC token + pbkdf2）/ 三档角色 403 / 检索密级白名单 + PATCH 即时同步 / 前端登录与角色感知 UI | [docs/mvp3](./docs/mvp3/README.md) |

### 安全模型（MVP3 落地）

```
POST /api/auth/login（pbkdf2，错密码/未知/禁用统一 401 防枚举）
  → Bearer token（HMAC-SHA256 无状态，12h；role/tenant 以 DB 行为准，禁用/改密立即生效）
  → 三档角色：admin / editor（可写）· viewer（只读，写路径一律 403）
  → 检索强制过滤 4 条：tenant_id + is_latest + is_deleted + access_level ∈ 角色白名单
     （viewer 不可见 confidential；请求参数只能收窄白名单）
  → PATCH access_level 同步该文档全部 Qdrant 点（失败 503 + MySQL 回滚）
  → 写路径全程审计（audit_logs：action/actor/detail，GET /api/audit-logs 可查）
```

- 渐进开关：`SECURITY__AUTH_REQUIRED=false`（dev 默认）时无 token 回退 stub admin，**带 token 恒严格校验**；生产置 `true` 全强制。
- 数据：MySQL 现为 **10 张表**（迁移 0001–0004，`audit_logs` 为 0003、`users.password_hash` 为 0004）。

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
alembic upgrade head                # 建 10 张表（迁移 0001–0004）
python scripts\seed.py              # 种子数据：默认租户/admin（密码缺省 admin123，可用 RAGIMS_ADMIN_PASSWORD 覆盖）/数据源/Embedding 模型
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

1. 浏览器打开 `http://localhost:5173` —— 自动跳转登录页，用 `admin` / `admin123`（或你 seed 时设的密码）登录。
2. 拖入一个 pdf/docx/txt 上传 —— 任务看板出现新 job，约几十秒后变 **succeeded**。
3. 「检索测试」页用文档里的原句搜索 —— 能返回带分数的命中。
4. 也可以直接验证 API：`http://localhost:8000/docs`（Swagger UI；业务接口需 `Authorization: Bearer <token>`，`SECURITY__AUTH_REQUIRED=false` 时匿名亦可）。

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
| `SECURITY__AUTH_REQUIRED` | 强制登录（false 时无 token 匿名回退 stub，带 token 恒严格校验） | false |
| `SECURITY__TOKEN_SECRET` | HMAC token 签名密钥（生产必改，≥32 字节随机串） | dev-only-insecure-secret-change-me |
| `SECURITY__TOKEN_TTL_SECONDS` | token 有效期 | 43200（12h） |
| `RAGIMS_ADMIN_PASSWORD`（seed 时） | admin 初始密码 | admin123 |
| `VITE_API_BASE_URL`（前端） | API 前缀 | http://127.0.0.1:8000/api |

## 常见问题（FAQ）

- **启动即 ValidationError**：`.env` 缺 `OPENAI__API_KEY`；或 `OPENAI__EMBEDDING_DIMENSION` 与既有 collection 维度不一致（重建 collection，见 runbook）。
- **上传返回 413**：超过 50MB；415：类型不符（支持 pdf/docx/txt/md）。
- **任务一直 pending**：Celery worker 未启动；`celery inspect ping` 无响应说明 broker/队列问题。
- **Windows worker 建议 `--pool solo`**：prefork 在 Windows 不可用。
- **接口 401**：token 缺失/过期/用户被禁用——重新登录（前端会自动跳登录页）；`SECURITY__AUTH_REQUIRED=true` 时无 token 一律 401。
- **接口 403**：当前角色无写权限（viewer 只读）；写操作需 admin/editor。
- **机密文档搜不到**：viewer 检索 confidential 按设计不可见；admin 可见。若 admin 也搜不到，用 runbook 对账脚本查 Qdrant 点数。
- **前端 CORS 报错**：`APP__CORS_ORIGINS` 需含 `http://localhost:5173`。

## 质量与 CI

- 后端门禁：`pytest`（**318 单测** + marker-gated 真栈集成 `test_i1/test_j/test_k_integration.py`，`RAGIMS_INTEGRATION=1` 运行）、`ruff`、`black`、`mypy`；前端 `tsc --noEmit`。
- CI：`.github/workflows/ci.yml`（lint + test + 覆盖率 ≥70%，前端 typecheck + build）。
- 验收探针（阶段收官时跑通，验收后可删）：`backend/scripts/_j*_tmp.py`、`_k6e2e_tmp.py`。
