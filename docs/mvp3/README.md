# MVP3（阶段 3 · 权限与多租户）任务索引

> 对应 `plan.md` 八/阶段 3「权限与多租户（3-4 周）」。阶段代号 **K**，接续 MVP2 的 J 阶段。
> 文档风格沿用 [docs/mvp2/](../mvp2/README.md)。

## 现状盘点（截至 MVP2 完成）

| plan.md 阶段 3 任务 | 现状 | 缺口 → 承接任务 |
| :-- | :-- | :-- |
| 租户隔离 | ✅ 已有：所有 API 经 `get_current_user().tenant_id` 强制过滤，跨租户 404 有测试 | 认证从 stub 换成真实登录 → **K2** |
| 角色/用户权限 | ⚠️ `users.role` 字段已有（admin），`CurrentUser.role="admin"` 写死；无登录、无 403 | **K2 + K3** |
| ACL 同步 | ❌ `documents.access_level` 已进 Qdrant payload，但 `PATCH access_level` 只改 MySQL（J3 遗留） | **K4** |
| 检索过滤 | ⚠️ 硬过滤 tenant + is_latest + is_deleted 已有；**access_level 不过滤**（viewer 可检索机密） | **K4** |
| 审计日志 | ❌ `audit_logs` 表未建，写路径无埋点 | **K1** |

**核心设计决策：**

1. **角色三档够用**：`admin`（全权）/ `editor`（读写文档）/ `viewer`（只读+检索）——资源级 ACL 表（plan.md 4.7 `permissions`）**延后**，MVP3 用 role + 文档 access_level 覆盖场景。
2. **认证 = Bearer token**：`POST /auth/login`（username/password）签发 HMAC token（无状态、含 tenant/user/role/过期）；`get_current_user` 从 token 解析，替换 stub。不引入 OAuth/JWT 库（标准库 HMAC 足够，边界见 K2）。
3. **审计只记写路径**：upload/patch/activate/version-delete/soft-delete/reprocess/login 失败——读路径不记（量太大无价值）。
4. **检索过滤是安全边界**：viewer/editor 检索时按「角色允许的密级白名单 ∩ 文档 access_level」加 Qdrant `must` 条件；access_level 变更必须同步点 payload（K4 补齐 J3 缺口）。

## 阶段 K · 权限与多租户（已完成 ✅）

| 任务 | 文件 | 说明 | 状态 |
| :--- | :--- | :--- | :-- |
| K1 | [审计日志](k1-audit-logs.md) | audit_logs 表 + 埋点 + GET /audit-logs | ✅ |
| K2 | [认证落地](k2-auth-login.md) | /auth/login + Bearer token + get_current_user 真实现 | ✅ |
| K3 | [角色权限](k3-roles-permissions.md) | 三档角色 + require_writer + 写路径 403 | ✅ |
| K4 | [检索 ACL 与密级同步](k4-search-acl.md) | 密级白名单过滤 + PATCH access_level 同步点 | ✅ |
| K5 | [前端登录与权限](k5-frontend-auth.md) | 登录页 + token 注入 + 401/403 处理 | ✅ |
| K6 | [测试与验收](k6-tests-acceptance.md) | 单测 + 真栈集成 + 探针 + 文档收官 | ✅ |
| K7 | [用户管理 API](k7-user-management.md) | admin-only 建号/列表/PATCH + 审计 + 防自锁 + 前端 Tab | ✅ |

**阶段达成标志（K6 验收，全部实测）：** 登录才能调 API（`SECURITY__AUTH_REQUIRED` 渐进开关）；viewer 写 403 全矩阵；viewer 检索不到机密文档且 PATCH 密级即时生效（无 reprocess）；写路径审计可查（action/actor/detail）；门禁 pytest **318 passed**（+31 单测，6 skipped 含集成）、ruff/black/mypy/tsc 全绿、K6 E2E 探针 exit 0。

**依赖**：K1 独立可并行；K2 → K3 → K4 → K5；K6 收尾。关键路径 **K2 → K3 → K4 → K6**。

## 交付物（达成标志）

- 登录才能调 API；viewer 写操作 403
- viewer 检索不到机密文档（access_level 过滤生效，含 PATCH 密级后立即生效）
- 写路径全程审计可查（action/actor/detail）
- 租户隔离回归全绿（token 中的 tenant 不可伪造）
