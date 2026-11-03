# Runbook · 运维手册

面向开发/值班：任务失败排查、Qdrant 重建、MinIO 清理、常用命令。

> 约定：`backend/` 下运行，venv 已激活（`.\env\Scripts\Activate.ps1`）；探针脚本 `backend/scripts/_*e2e_tmp.py` 为临时验收工具。

## 1. 任务失败排查

### 定位三步

```powershell
# ① 看任务与步骤（哪一步、什么错误）
curl http://127.0.0.1:8000/api/jobs/{job_id}
curl http://127.0.0.1:8000/api/jobs/{job_id}/steps   # 每步 status/duration_ms/error_message

# ② worker 是否活着
.\env\Scripts\celery.exe -A app.workers.celery_app inspect ping
.\env\Scripts\celery.exe -A app.workers.celery_app inspect active      # 卡在什么任务

# ③ 日志（loguru 落盘）
Get-Content logs\*.log -Tail 50 | Select-String "\[pipeline\]|ERROR"
```

### 常见失败与处置

| 现象 | 根因 | 处置 |
| :-- | :-- | :-- |
| `parse` 步 failed | 加密/损坏 PDF、扫描件 | 换文件；加密 PDF 需密码（不支持的走 failed，属预期） |
| `embed` 步 failed | API key/限流/网络 | 看 `error_message`；429/5xx 由任务基类自动重试（双层），耗尽后人工 `POST /jobs/{id}/retry` |
| `upsert` 步 failed | Qdrant 维度不匹配 / 宕机 | 见 §2 重建；确认 `OPENAI__EMBEDDING_DIMENSION` 与 collection 一致 |
| job 一直 pending | worker 未启动 / broker 断 | 启动 worker；`redis-cli ping` 验证 |
| job running 卡死 | worker 被杀（solo pool 单进程） | 重启 worker；任务超时后 Celery 重投（幂等安全） |
| 大量 413/415 | 客户端传错文件 | 前端已做类型/大小预校验，检查前端版本 |

### 重试 / 取消

```powershell
# 失败任务重投（产生新 job 行，复用 doc_version_id）
curl -X POST http://127.0.0.1:8000/api/jobs/{job_id}/retry

# 协作取消（仅 pending/running；worker 在步骤边界检查取消标志）
curl -X POST http://127.0.0.1:8000/api/jobs/{job_id}/cancel
```

## 2. Qdrant 重建

**何时**：collection 维度变更（换 embedding 模型）、数据错乱、对账发现大规模丢点。

```powershell
# ① 对账：MySQL vs Qdrant 差异报告（不写入）
.\env\Scripts\python.exe scripts\reconcile.py --dry-run    # 参数以脚本 -h 为准

# ② 删除并重建 collection（维度来自当前配置）
.\env\Scripts\python.exe scripts\init_qdrant.py --recreate

# ③ 回填：对每个 succeeded 版本重跑向量化（重处理 API 或直接重投 job）
#    方式 A：对受影响文档逐个 POST /api/documents/{id}/reprocess
#    方式 B：批量——见 scripts/reconcile.py 的 --repair（补点/删孤儿）
```

> 注意：重建后**必须**回填，否则检索为空；回填期间检索结果不完整属预期。

## 3. MinIO 清理

```powershell
# 对象键结构：
#   raw-docs/{tenant}/{doc_id}/{version}/{file_name}     原始文件
#   parsed-text/{version_id}.json                        解析文本

# 软删除文档的对象（MVP 异步清理未实现，手工删）：
mc alias set ragims http://localhost:9000 minioadmin minioadmin
mc rm --recursive --force ragims/raw-docs/{tenant}/{doc_id}/

# parsed 文本孤儿（版本行已删但对象残留）：按 DB 版本表对账后删除
mc ls ragims/parsed-text/ | ForEach-Object { ... }   # 与 document_versions 比对
```

**误删恢复**：MinIO 无版本化（MVP），raw 对象删除不可恢复；parsed 文本可由 raw 重新解析生成（重跑 reprocess）。

## 4. 常用命令速查

```powershell
# 服务
.\env\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
.\env\Scripts\celery.exe -A app.workers.celery_app worker -Q parse,embed,default -l info --pool solo
.\env\Scripts\celery.exe -A app.workers.celery_app flower --port=5555

# 数据
alembic upgrade head                       # 迁移
.\env\Scripts\python.exe scripts\seed.py   # 种子（租户/用户/默认模型）
.\env\Scripts\python.exe scripts\init_qdrant.py
.\env\Scripts\python.exe scripts\reconcile.py

# 质量门禁
.\env\Scripts\python.exe -m pytest tests -q -p no:cacheprovider        # 247 单测
$env:RAGIMS_INTEGRATION='1'; pytest tests\test_i1_integration.py -q    # 真栈集成
.\env\Scripts\ruff.exe check app tests scripts
.\env\Scripts\black.exe --check app tests
.\env\Scripts\mypy.exe app scripts/seed.py --cache-dir $env:TEMP\mypy_cache_ragims
```

## 5. 紧急预案

- **Redis 宕机**：上传接口 503（`ERR_UNAVAILABLE`），前端友好提示；恢复后 pending 任务自动继续消费。
- **MySQL 宕机**：全接口 500；恢复后重试上传（幂等保证不重复）。
- **Embedding 网关宕机**：embed 步失败 + 自动重试耗尽后 job failed；网关恢复后批量 retry failed jobs。
- **Qdrant 数据丢失**：见 §2 重建 + 回填（reprocess 全量 succeeded 文档）。
