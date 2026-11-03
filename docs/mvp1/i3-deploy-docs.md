# I3 · 部署与文档

> **阶段**：I 测试、联调、验收（3-4 天）　**依赖**：全部　**工时**：约 1 天

## 目标

产出生产示例编排与项目文档。

## 实施步骤

### 1. `deploy/` 生产示例
- compose 生产示例（含资源限制）。

### 2. 文档
- `README.md`：本地启动、环境变量、常见问题。
- `docs/api.md`：接口清单与示例（可由 OpenAPI 导出）。
- `docs/runbook.md`：任务失败排查、Qdrant 重建、MinIO 清理。

## 验收标准

- [x] compose 生产示例要有指示文件，可不直接运行，通过手工去启动。
- [x] README/API/Runbook 齐备。

## 产出物（I3 完成）

| 文件 | 内容 |
| :-- | :-- |
| `deploy/docker-compose.prod.yml` | 生产示例（指示性文件，**默认不自动运行**）：头部注释含 4 步手工启动流程（.env → 基础设施 → alembic/seed/init_qdrant → backend/worker/flower）；资源限制（cpu/mem limits + reservations）、backend `--workers 2`、worker `replicas: 2`（可 `--scale worker=N` 扩容）、生产凭据全部 `${VAR:?}` 强制注入、独立 `prod_*` 命名卷；YAML 语法已校验（7 services） |
| `README.md`（根，重写） | 架构文本图（前端→API→队列→七步流水线→存储）、本地启动三步（compose/后端/前端）、环境变量表（含必填项与默认值）、6 条 FAQ（ValidationError/413/415/pending/Windows solo pool/CORS）、质量与 CI 说明 |
| `docs/api.md` | **由 live OpenAPI 自动生成**（生成脚本运行时拉取，人工复核落盘）：7 组接口 18 端点表、错误码速查（11 个 ERR_*）、curl 请求/响应示例（upload/search/jobs steps） |
| `docs/runbook.md` | 任务失败排查三步法（API→celery inspect→日志）+ 6 种常见失败处置表 + retry/cancel 命令；Qdrant 重建（对账→recreate→回填）；MinIO 清理（对象键结构、软删残留、孤儿 parsed 文本、误删恢复边界）；命令速查 + 4 项紧急预案 |

## 关联任务

- 依赖全部阶段。
