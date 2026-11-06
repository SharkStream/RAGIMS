# K5 · 前端登录与权限

> **阶段**：K 权限与多租户　**依赖**：K2、K3　**工时**：约 0.5-1 天

## 目标

前端接入真实登录；401/403 有统一体验；viewer 看不到写按钮。

## 现状

前端所有请求裸调（后端 stub 不校验）；无登录页；401/403 无处理。

## 实施步骤

1. `src/api/client.ts`：请求拦截器注入 `Authorization: Bearer <token>`；响应 401 → 清 token 跳登录页；403 → `message.error`（ERR_FORBIDDEN 文案）。
2. 登录页 `/login`：用户名/密码表单 → `authApi.login` → 存 localStorage（`ragims.token`）→ 跳转首页。
3. 路由守卫：无 token 一律重定向 /login（main.tsx 包一层）。
4. 角色感知 UI：`CurrentUser` 由 `/auth/me`（K2 顺带提供）获取并缓存；`role === "viewer"` 时隐藏/禁用写按钮（上传、编辑元数据、删除、重处理、版本操作）。
5. `tsc --noEmit` 零错误。

## 验收标准

- [x] 未登录访问任何页 → 重定向登录；登录后正常使用
- [x] viewer 登录后写按钮隐藏，直接调 API 返回 403 有提示（client.ts 中文文案 + 后端 K3 实测）
- [x] 退出登录（清 token）回登录页

## 产出物（K5 完成）

| 位置 | 内容 |
| :-- | :-- |
| `src/auth.ts` | token/user 存取（localStorage `ragims_token/ragims_user`）+ `canWrite()` |
| `src/api/client.ts` | 请求拦截器注入 Bearer；响应 401（非登录调用）→ 清会话跳 `/login?next=` |
| `src/api/index.ts` | `authApi.login / authApi.me` |
| `src/pages/login.tsx` | 登录页（深链回跳 `next`、后端统一错误文案） |
| `src/App.tsx` | `RequireAuth` 路由守卫 + 头像身份展示 + 退出登录 |
| `src/pages/documents.tsx` | viewer 隐藏：上传区、重新处理、软删除、编辑元数据、设为当前、删除版本 |
| `src/pages/jobs.tsx` | viewer 隐藏：重试、取消 |

`tsc --noEmit` 零错误；后端回归 318 passed 不受影响。

## 关联任务

- 依赖 [K2](k2-auth-login.md)、[K3](k3-roles-permissions.md)；错误文案复用 `errorMessage()`。
