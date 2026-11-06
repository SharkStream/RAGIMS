# L1 · 质量数据层

> **阶段**：L 质量与评估　**依赖**：无（基于阶段 3 基线）　**工时**：约 0.5 天
> 表设计来源：[plan.md §4.8](../../plan.md)

## 目标

把 plan.md 延后至阶段 4 的两张表落地：`quality_checks`（版本级质量检查结果）
与 `evaluation_runs`（检索评估基准），迁移 **0005**（接在 0004 之后）。

## 实施步骤（完成 ✅）

1. `app/models/quality_check.py`：`doc_version_id`（FK → document_versions，**CASCADE**——
   版本级删除时 DB 兜底清理检查行）、`check_type`、`score`（归一 [0,1]）、`detail`（原始计数）、
   无 updated_at（检查结果不可变，重跑覆盖式重建）；索引 `(doc_version_id, check_type)`。
2. `app/models/evaluation_run.py`：`tenant_id/user_id/name/dataset/metrics/result`、
   无 updated_at（**重跑即新行**，保留历史趋势）；索引 `(tenant_id, created_at)` 倒序查询。
3. `alembic/versions/0005_quality_evaluation.py`：两表 DDL（MySQL 8，CHAR(36) PK，
   DATETIME(3) naive UTC，与全库约定一致）。
4. `tests/test_b2_models.py`：`STAGE4_TABLES` 纳入 metadata 清单断言；
   `DEFERRED_TABLES` 移除这两张。

## 验收标准

- [x] 迁移 0005 上下行可执行（live MySQL 已应用：quality_checks ✓ / evaluation_runs ✓，全库 13 张表含 alembic_version）
- [x] `test_b2_models.py` 53 例全绿（metadata 清单 = 9 MVP + audit_logs + 2 新表）
- [x] 与全库约定一致：FK 命名 / InnoDB utf8mb4 / DATETIME(3) / JSON 可空

## 关联任务

- 被 [L2](l2-quality-checks.md)（写 quality_checks）、[L3](l3-evaluation-engine.md)（写 evaluation_runs）消费。
