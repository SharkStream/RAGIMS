# K7 · 注册与用户管理 API（阶段 3 增量）

> **阶段**：K 权限与多租户（增量）　**依赖**：K1-K3　**工时**：约 0.5 天
> 设计来源：[plan.md 阶段 3 增量节](../../plan.md)

## 目标

账号生命周期从 CLI（`scripts/create_user.py`）升级为正式 API：admin 在本租户内
创建 / 查看 / 维护用户（角色、状态、密码），全部变更进审计。

## 实施步骤（完成 ✅）

1. `app/core/permissions.py` 新增 `require_admin`（非 admin → 403 `ERR_FORBIDDEN`）。
2. `app/schemas/user.py`：`UserCreateRequest`（用户名 pattern / 密码 ≥8 / 角色枚举）、
   `UserPatchRequest`（role/status/password 三选）、`UserOut`（**不含 password_hash**）。
3. `app/api/auth.py` 三个端点（均 admin-only）：
   - `POST /auth/users`：建号（重名 409、密码强度 422、审计 `auth.user_created`）
   - `GET /auth/users`：本租户分页列表（status 过滤；不回传哈希）
   - `PATCH /auth/users/{id}`：改角色（`auth.role_changed` from→to）/ 启禁用
     （`auth.user_disabled`/`auth.user_enabled`）/ 重置密码（`auth.password_reset`，
     **不落明文**）；跨租户目标 404；**修改自己 409（防自锁，且不触发 DB 读取）**
4. 前端：设置页新增「用户管理」Tab（仅 admin 可见）：
   列表 + 新建 Modal + 行内改角色 / 启禁用（Popconfirm）/ 重置密码 Modal；
   当前账号行只读（与后端防自锁呼应）。
5. 单测 13 例（offline，`dependency_overrides` 隔离身份与 DB）+ live 探针。

## 验收标准（对齐 plan.md 验收链）

- [x] admin 建号 → 新用户登录（探针 step 2/5：201 → login 200）
- [x] 降级 viewer → **同一 token** 立即写 403（step 6，role 每次查库）
- [x] 禁用 → 旧 token 401 + 重登录 401（step 7，status 每次查库）
- [x] 全程审计可查（step 9：user_created / role_changed(detail from→to) / user_disabled）
- [x] 门禁：pytest **331 passed**（+13）、ruff / black / mypy / tsc 全绿、探针 10 步 exit 0

## 产出物

| 位置 | 内容 |
| :-- | :-- |
| `app/api/auth.py` | + create_user / list_users / patch_user（K7 段） |
| `app/core/permissions.py` | + `require_admin` |
| `app/schemas/user.py` | + UserCreateRequest / UserPatchRequest / UserOut |
| `frontend/src/components/UserManagementTab.tsx` | 用户管理 Tab（列表/新建/改角色/启禁用/重置密码） |
| `frontend/src/pages/settings.tsx` | Tabs 化：通用设置 + 用户管理（admin） |
| `frontend/src/api/index.ts` | + `usersApi` + `ManagedUser` |
| `tests/test_k7_users.py` | 13 例：创建/审计/弱密码/重名/403 矩阵/列表脱敏/role_changed/禁用启用/密码重置脱敏/跨租户 404/自改 409/空 PATCH 400/非法角色 422 |
| `scripts/_k7e2e_tmp.py` | live 探针（10 步，验收后可删） |
| `scripts/create_user.py` | CLI 建号（K7 前置产物，保留） |

## 关联任务

- 依赖 [K2](k2-auth-login.md)（token/查库语义）、[K3](k3-roles-permissions.md)（角色）、
  [K1](k1-audit-logs.md)（审计埋点模式）。
