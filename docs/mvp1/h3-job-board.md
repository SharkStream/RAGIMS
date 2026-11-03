# H3 · 任务看板

> **阶段**：H 前端管理界面（5-6 天）　**依赖**：H1、G1　**工时**：约 1.5 天

## 目标

实现任务列表与步骤时间线，支持重试/取消与轮询刷新。

## 实施步骤

### 1. 列表 `frontend/src/pages/Jobs/index.tsx`
- 状态标签、耗时、创建时间、筛选。

### 2. 详情
- 步骤时间线（parse/clean/chunk/embed/upsert），每步状态与错误。

### 3. 操作
- 重试 / 取消。

### 4. 刷新
- 简易轮询刷新（MVP 不做 WebSocket）。

## 验收标准

- [x] 任务列表与步骤时间线可视化完整。
- [x] 重试/取消可用。
- [x] 轮询刷新生效。

## 产出物（H3 完成）

- `src/pages/jobs.tsx` — 任务看板：
  - **列表**：状态 Tag（排队/运行/成功/失败/取消）+ 耗时列（`finished_at - started_at`，运行中显示 —）+ 创建时间 + 筛选（状态 / job_type / doc_id）；
  - **详情抽屉**：任务 Descriptions（状态/类型/doc_id 可复制/Celery task id/耗时/错误）+ `Steps` 垂直时间线（七步：每步状态色、`duration_ms`、错误红字、output JSON 折叠展开，Spin 加载）；
  - **操作**：重试（仅 failed 显示，Popconfirm → POST /retry 提示新 job id）、取消（仅 pending/running 显示 → POST /cancel）；
  - **轮询**：5s `setInterval` 刷新列表 + 打开中的详情步骤（Switch 可关）。
- **后端修复**（live 探针发现）：`app/workers/base.py` 此前从不写 `ingestion_jobs.started_at/finished_at`（job 级耗时恒空，G1 JobOut 两字段一直为 null）——`_set_job_status` 首次进入 running 时盖章 `started_at`、failed 时补 `finished_at`，`finish_job` 成功路径补 `finished_at`；相应补 4 处测试 stub 字段（`test_f1_task_base.py` / `test_f2_pipeline.py` / `test_f3_trigger.py` ×2）。

## 验收证据（live，real exit 0）

| # | 场景 | 实测 |
| :- | :--- | :--- |
| 1 | 列表筛选（status+type+doc_id） | 命中目标 job，`started_at/finished_at` 已盖章 |
| 2 | 步骤时间线 | 七步 `parse→clean→chunk→persist_chunks→embed→upsert→write_back`，每步 `duration_ms` 非空 |
| 3 | 失败重试 | 加密 PDF → job failed → retry 201 → 新 job pending |
| 4 | 取消 | queued job → cancelled；对 succeeded job 取消 → 409（按钮本就隐藏） |

门禁：pytest **243 passed**、ruff/black/mypy 全绿（92 文件）。

> **注意**：worker 需重启一次以加载 `started_at/finished_at` 修复（celery 无 --reload）：重跑您启动 worker 的那条命令即可。

## 关联任务

- 依赖 [H1](h1-frontend-init.md)、[G1](g1-job-api.md)。
