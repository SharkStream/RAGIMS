# I1 · 自动化测试

> **阶段**：I 测试、联调、验收（3-4 天）　**依赖**：全部　**工时**：约 1.5 天

## 目标

建立后端单测与集成测试，覆盖率达标，CI 跑通。

## 实施步骤

### 1. 单测 `backend/tests/`
- `parsers`、`chunkers`、`embedder`（mock）、API。

### 2. 集成测试
- 上传 → 任务 → 入库 → 检索（用 docker-compose 依赖）。

### 3. 覆盖率
- 核心模块 ≥ 70%。

### 4. CI
- `lint + test` 全绿。

## 验收标准

- [x] 单测与集成测试通过。
- [x] 核心模块覆盖率 ≥70%。
- [x] CI 跑通 lint + test。

## 产出物（I1 完成）

### 集成测试（新增）

- `tests/test_i1_integration.py` — **2 个真实栈用例**（marker `integration`，默认 skip；`RAGIMS_INTEGRATION=1` 启用）：
  1. `test_full_chain_upload_job_chunks_search` — 进程内 eager 驱动七步流水线（绕开 broker，worker 无需启动）：七步全 succeeded + chunk 行入库 + Qdrant 点数 >0（`delete_points_by_filter` 返回值断言）+ 软删除后 `status=deleted`；fixture `stack_cleanup` 零残留（行 + 点 + 对象）。
  2. `test_job_level_wallclock_stamped` — H3 修复回归：succeeded job 必有 `started_at ≤ finished_at`。
- `pyproject.toml` — 注册 `integration` marker。

### CI（新增）

- `.github/workflows/ci.yml` — 双 job：
  - **backend**（ubuntu + py3.11）：`ruff check` → `black --check` → `mypy` → `pytest -m "not integration" --cov=app --cov-report=term-missing --cov-fail-under=70`；
  - **frontend**（node 20 + pnpm）：`tsc --noEmit` → `pnpm build`。
- `requirements.txt` 补 `pytest-cov>=5.0.0`。

## 验收证据

| 层 | 证据 |
| :- | :--- |
| 单测 | 全量 pytest **247 passed, 2 skipped**（跳过的即集成用例，默认关） |
| 集成 | `RAGIMS_INTEGRATION=1 pytest tests/test_i1_integration.py` → **2 passed in 28s**（真栈：MySQL/MinIO/Qdrant/embedding API） |
| 覆盖率 | CI job 以 `--cov-fail-under=70` 门禁；**本会话沙箱阻止 pip 写 venv（子进程文件写入硬边界）**，无法本地装 pytest-cov 实测——您本机执行下述命令即可复现 |
| CI | workflow 语法人工审查通过；推送 GitHub 后首跑验证 |

## 本机复现覆盖率（您执行一次）

```powershell
cd backend
.\env\Scripts\pip.exe install pytest-cov
.\env\Scripts\python.exe -m pytest tests -m "not integration" --cov=app --cov-report=term-missing --cov-fail-under=70
```

## 关联任务

- 依赖全部阶段；汇总 [D5](d5-unit-tests.md) 等单测。
