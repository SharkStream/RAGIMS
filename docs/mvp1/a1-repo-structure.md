# A1 · 仓库与工程结构

> **阶段**：A 项目脚手架与基础设施（3-4 天）　**依赖**：无　**工时**：约 1 天

## 目标

初始化 monorepo 目录与后端工程骨架，统一配置、日志与代码规范，为后续所有阶段提供一致的基础设施。

## 目录结构

```
RAGIMS/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── main.py          # 应用入口
│   │   ├── api/             # 路由层（routers）
│   │   ├── core/            # config.py / logging.py / deps.py / celery_app.py
│   │   ├── models/          # SQLAlchemy 模型
│   │   ├── schemas/         # Pydantic 模型
│   │   ├── services/        # 业务逻辑
│   │   ├── workers/         # Celery 任务
│   │   ├── parsers/         # 文档解析器
│   │   ├── chunkers/        # 切分器
│   │   ├── clients/         # MinIO / Qdrant / OpenAI 客户端封装
│   │   └── utils/
│   ├── alembic/             # 数据库迁移（B2 初始化）
│   ├── tests/
│   ├── pyproject.toml       # Poetry 锁定依赖
│   └── requirements.txt
├── frontend/                # React + Vite（H1 初始化）
├── deploy/                  # docker-compose 等部署编排
└── docs/                    # 文档（本 tasks 目录位于 docs/tasks/）
```

## 实施步骤

### 1. 创建 monorepo 目录
- 建立 `backend/`、`frontend/`、`deploy/`、`docs/` 四个顶层目录。

### 2. 后端依赖锁定
- `backend/pyproject.toml`（Poetry）+ 导出的 `requirements.txt`。
- 核心依赖：`fastapi`、`uvicorn[standard]`、`sqlalchemy>=2.0`、`alembic`、`pydantic>=2`、`pydantic-settings`、`celery`、`redis`、`pymysql`（或 `asyncmy`）、`minio`、`qdrant-client`、`openai`、`pymupdf`、`python-docx`、`chardet`、`tiktoken`、`loguru`、`python-multipart`。

### 3. 后端目录分层
- 在 `backend/app/` 下建立 `api/`、`core/`、`models/`、`schemas/`、`services/`、`workers/`、`parsers/`、`chunkers/`、`clients/`、`utils/`，每层放 `__init__.py`。

### 4. 统一日志配置
- 文件：`backend/app/core/logging.py`
- 使用 loguru，JSON 结构化输出；提供 `setup_logging()`，在 `main.py` 启动时调用。

### 5. 统一配置管理
- 文件：`backend/app/core/config.py`
- 基于 `pydantic-settings`，从 `.env` 读取；暴露 `Settings` 单例 `settings`。
- 分组：`[mysql]`、`[redis]`、`[qdrant]`、`[minio]`、`[openai]`、`[app]`。

### 6. 代码规范
- `.gitignore`、`.editorconfig`、`.pre-commit-config.yaml`。
- 工具链：`ruff`（lint）+ `black`（format）+ `mypy`（type check）。

## 验收标准

- [ ] `backend/`、`frontend/`、`deploy/`、`docs/` 目录就位，后端各分层含 `__init__.py`。
- [ ] `settings` 能从 `.env` 读取配置，缺项有明确报错。
- [ ] `pre-commit run --all-files` 可正常通过。

## 关联任务

- 产出被 [A2 本地开发环境](a2-local-env.md)、[A3 FastAPI 骨架](a3-fastapi-skeleton.md) 依赖。
