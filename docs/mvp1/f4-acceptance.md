# F4 · 阶段 F 验收标准

> **阶段**：F Celery 任务流水线　**依赖**：F1–F3

## 验收清单

- [x] 上传后任务自动流转至 success。
- [x] `job_steps` 每步有耗时与 output。
- [x] 人为制造解析失败，任务状态为 failed 且 error_message 可读。
- [x] 重试机制生效（可 mock 外部依赖失败验证）。

## 验收证据（F4 综合探针，真 worker + broker，real exit 0）

| # | 清单项 | 实测 |
| :- | :--- | :--- |
| 1 | 自动流转 success | 上传 txt → `pending → running → succeeded`，7 步共 **1834 ms**，`celery_task_id` 回写 |
| 2 | 步骤耗时 + output | 7 条 job_steps 全有 `started_at/finished_at`（finished ≥ started）+ 非空 output |
| 3 | 失败可读 | 加密 PDF → job `failed`，error_message=`ValueError: PDF is password-protected: cannot extract text w…` |
| 4 | 重试生效 | 配置断言（`autoretry_for=(Exception,), retry_backoff=2, max_retries=3`）+ 失败 job 留 **2 条 parse 尝试** audit 行；瞬时依赖失败的 mock 验证由离线测试（F1/F2 用例）覆盖 |

达成标志 ✅：上传→解析→清洗→切分→embedding→Qdrant 全链路在任务队列中自动执行，M2「后端闭环」成立。

## 关联任务

- 上游：[F1](f1-celery-base.md)–[F3](f3-trigger.md)。
- 下游：[G 任务/检索测试 API](g1-job-api.md)。
