# K3 · 角色权限（三档角色 + 403）

> **阶段**：K 权限与多租户　**依赖**：K2　**工时**：约 0.5 天

## 目标

viewer 只读、editor 读写、admin 全权——写路径统一 403 语义。

## 现状

`CurrentUser.role` 已存在但无人消费；所有 API 对任何身份全开。

## 实施步骤

1. `app/core/permissions.py`：`Role`（admin/editor/viewer）+ `WRITER_ROLES = {admin, editor}` + `require_writer` 依赖（role 不在集合 → 403 `ERR_FORBIDDEN`）。
2. 写路径接入 `require_writer`：upload / patch / activate / version-delete / soft-delete / reprocess / job retry+cancel。
3. admin-only（可选记录）：无（MVP3 不做用户管理 API，seed 建用户）。
4. 错误码：`ERR_FORBIDDEN` 进 errorMessage 映射（403 文案）。
5. 单测：viewer 上传/PATCH/删除/activate 全 403；读路径（list/detail/versions/chunks/search/jobs）全放行；admin/editor 全放行。

## 验收标准

- [x] viewer 一切写操作 403、读操作正常
- [x] editor 可写文档、admin 同
- [x] 403 错误码/文案统一（后端 `ERR_FORBIDDEN`；前端 client.ts 同步映射）

## 产出物（K3 完成）

| 位置 | 内容 |
| :-- | :-- |
| `app/core/permissions.py` | `WRITER_ROLES = {admin, editor}` + `require_writer` 依赖（403 `ERR_FORBIDDEN`）+ K4 预置 `ACCESS_LEVELS_BY_ROLE`（viewer 不可见 confidential） |
| `app/api/documents.py` | 7 个写端点换 `require_writer`：upload / patch / activate / version-delete / soft-delete / reprocess / cancel |
| `app/api/jobs.py` | retry / cancel 换 `require_writer`（读路径不动） |
| `frontend/src/api/client.ts` | `ERR_UNAUTHORIZED` / `ERR_FORBIDDEN` 中文文案 |
| `tests/test_k3_roles.py` | 4 个单测：viewer 九条写路径全 403、admin/editor 过门禁（stub 服务）、读路径放行、helper 矩阵 |

## 验收证据（live，real）

| # | 场景 | 结果 |
| :- | :--- | :--- |
| 1 | admin 登录 + 读列表 | 200 |
| 2 | 新建 viewer 用户（真 DB 行）→ /auth/me 返回 role=viewer | ✓ |
| 3 | viewer upload / PATCH → **403 ERR_FORBIDDEN** | ✓ |
| 4 | viewer 读列表 → 200 | ✓ |

门禁：pytest **310 passed**（+4）· ruff / black / mypy 全绿。

## 关联任务

- 依赖 [K2](k2-auth-login.md)；K4 的密级白名单按 role 区分。
