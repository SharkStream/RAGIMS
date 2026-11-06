# K2 · 认证落地（/auth/login + Bearer token）

> **阶段**：K 权限与多租户　**依赖**：无　**工时**：约 0.5-1 天

## 目标

`get_current_user` 从「固定 admin stub」换成真实认证；租户身份不可伪造。

## 现状

`app/core/deps.py` 的 `get_current_user()` 返回写死的 seed 用户（注释明确 stage 3 替换）；`users` 表已有 `username/role/status`，**无 password 列**。

## 实施步骤

1. `users` 表补 `password_hash VARCHAR(255)`；`scripts/seed.py` 给默认 admin 设密码（env `RAGIMS_ADMIN_PASSWORD`，缺省 `admin123`）。
2. `app/core/security.py`：`hash_password/verify_password`（pbkdf2_hmac，标准库，不引 bcrypt）+ `issue_token(user)` / `parse_token(token)`（HMAC-SHA256 签名 payload `{tenant_id,user_id,role,exp}`，base64url；secret 来自 `settings.security.token_secret`，缺省随机并落 .env）。
3. API：`POST /api/auth/login`（username+password → `{token, expires_in, user}`）；禁用用户 401。
4. `get_current_user` 重写：HTTPBearer → parse_token → 查 users 行校验 status=active → CurrentUser（保留原字段）；无效/过期 → 401 `ERR_UNAUTHORIZED`。
5. 兼容：openapi 加 securitySchemes；前端仍可用（K5 接入前，测试用 `client` fixture 统一先登录拿 token）。
6. 单测：登录成功/密码错 401/禁用 401/无 token 401/篡改 token 401/过期 401/跨租户数据仍隔离。

## 验收标准

- [x] 全部现有 API 在无 token 时 401（`SECURITY__AUTH_REQUIRED=true` 时）；dev 默认 False 时匿名回退 stub（pre-K2 兼容），**带 token 则一律严格校验**
- [x] token 不可伪造（改 payload 任一字节 → 401）；过期 → 401；垃圾串 → 401
- [x] tenant/role 以 **users 行为准**（token 里旧 role 不生效）；禁用用户 token 立即失效

## 产出物（K2 完成）

| 位置 | 内容 |
| :-- | :-- |
| `alembic/versions/0004_users_password_hash.py` | `users.password_hash VARCHAR(255)`（已 upgrade 实测） |
| `app/core/config.py` | `SecuritySettings`：`auth_required`（dev 默认 False 渐进开关）/ `token_secret` / `token_ttl_seconds`（12h） |
| `app/core/security.py` | pbkdf2（200k 迭代 + 随机盐，标准库）+ HMAC-SHA256 签名 token（`{sub,user_id,tenant_id,role,iat,exp}`） |
| `app/api/auth.py` | `POST /auth/login`（统一 401 防枚举 + 审计 `auth.login`）+ `GET /auth/me` |
| `app/core/deps.py` | `get_current_user`：HTTPBearer → parse_token → **查 users 行**（status=active、role/tenant 以 DB 为准）→ CurrentUser |
| `scripts/seed.py` | 幂等回填 admin 密码（env `RAGIMS_ADMIN_PASSWORD`，缺省 admin123） |
| `tests/test_k2_auth.py` | 12 个单测（哈希回环 / token 篡改·过期·垃圾 / 登录四态 / DB role 优先 / 强制模式矩阵） |

## 验收证据（live，real）

| # | 场景 | 结果 |
| :- | :--- | :--- |
| 1 | 错密码登录 | 401 `ERR_UNAUTHORIZED` |
| 2 | 正确登录（seed admin123） | 200 + bearer token |
| 3 | `/auth/me` 带 token | 200，role=admin |
| 4 | 业务 API（/documents）带 token | 200 |
| 5 | 篡改 token | 401 |
| 6 | 登录产生 `auth.login` 审计行（K1 联动） | ✓ |

门禁：pytest **306 passed**（+12）· ruff / black / mypy 全绿。

## 关联任务

- K3（角色判定消费 `CurrentUser.role`）；K5（前端登录页）。
