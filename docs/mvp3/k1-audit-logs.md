# K1 · 审计日志（audit_logs + 埋点 + 查询 API）

> **阶段**：K 权限与多租户　**依赖**：无（独立可先行）　**工时**：约 0.5 天

## 目标

写路径全程留痕：谁在何时对什么资源做了什么，可分页查询。

## 现状

`audit_logs` 表未建（plan.md 4.7 延后项）；所有写 API 无任何留痕。

## 实施步骤

1. ORM：`app/models/audit_log.py`——`id/tenant_id/user_id/action/resource_type/resource_id/detail(JSON)/created_at`；索引 `(tenant_id, created_at)`。B 系列建表脚本同步（`scripts/` 建表或 ALTER）。
2. `app/services/audit_service.py`：`record_audit(session, *, tenant_id, user_id, action, resource_type, resource_id, detail=None)`——失败仅 log 不阻断主流程（审计不可用不应阻塞业务）。
3. 埋点（服务层成功 commit 后）：`doc.upload` / `doc.meta_patch`（detail 含变更字段）/ `doc.activate`（from→to）/ `doc.version_delete` / `doc.soft_delete` / `doc.reprocess`。
4. API：`GET /api/audit-logs`（分页 + action/resource_type 过滤，租户硬过滤）。
5. 单测：埋点产生行、detail 结构、跨租户不可见、分页。

## 验收标准

- [x] 上述每个写操作后 `audit_logs` 各有一行，actor/detail 正确
- [x] `GET /audit-logs` 分页 + 过滤正常；跨租户不可见（tenant 只取自身份）
- [x] 审计写入失败不阻断原操作（mock 异常验证：commit 炸 → rollback + log，无抛出）

## 产出物（K1 完成）

| 位置 | 内容 |
| :-- | :-- |
| `app/models/audit_log.py` + `alembic/versions/0003_audit_logs.py` | `audit_logs` 表：`(tenant_id, created_at)` 复合索引、MySQL JSON detail、只增不改（无 updated_at）；已 `alembic upgrade head` 实测 |
| `app/services/audit_service.py` | `record_audit`（best-effort：失败仅 log 不阻断业务）+ `list_audit_logs`（租户硬过滤 + action/resource_type/resource_id 过滤 + 倒序分页） |
| `app/api/audit.py` | `GET /api/audit-logs`；注册进 main.py |
| `app/api/documents.py` | 六个写端点埋点：upload / meta_patch（detail 含变更字段）/ activate（from→to）/ version_delete / soft_delete / reprocess |
| `tests/test_k1_audit.py` | 7 个单测（埋点形状 / 失败零埋点 / 分页过滤 / 租户取自身份 / 审计炸不阻断） |

## 验收证据（live，real）

| # | 场景 | 结果 |
| :- | :--- | :--- |
| 1 | HTTP 上传 → `doc.upload` 行（detail: file_name/version/duplicate） | ✓ |
| 2 | HTTP PATCH → `doc.meta_patch` 行（detail.fields = 实际变更字段） | ✓ |
| 3 | `GET /audit-logs?resource_id=` 精确召回 + action 过滤 | ✓ |
| 4 | 表结构：8 列 + `idx_audit_logs_tenant_created` | ✓（SHOW 验证） |

门禁：pytest **294 passed**（+7）· ruff / black / mypy 全绿。

## 关联任务

- 无前置依赖；K3 登录后 actor 从 token 来（当前用 stub CurrentUser 亦可先落地）。
