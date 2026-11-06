# K6 · 测试与验收（阶段 3 收官）

> **阶段**：K 权限与多租户　**依赖**：K1-K5　**工时**：约 0.5 天

## 目标

自动化验证 + 阶段验收，风格同 [J6](../mvp2/j6-tests-acceptance.md)。

## 实施步骤

1. **单测**（offline）：K1 埋点/分页/隔离；K2 登录/token 全语义；K3 三档角色 403 矩阵；K4 密级过滤 + 同步 + 503 回滚。目标 ≥20 用例。
2. **真栈集成**（`tests/test_k_integration.py`，marker-gated）：
   - 登录 → 上传 → PATCH 密级 → viewer 检索不可见 → 改回 → 可见；
   - viewer 写 403 全矩阵；审计行落库且 detail 正确。
3. **验收探针**（`scripts/_k6e2e_tmp.py`）：登录 → 双用户（admin/viewer）→ 上传机密文档 → viewer 检索查不到 → admin PATCH 密级 → viewer 检索可见 → viewer 写 403 → 审计日志可查（real exit 0）。
4. **文档收尾**：docs/mvp3/README 勾、todolist 阶段 K 全勾、api.md 补 /auth/login + /audit-logs、runbook 补「token/密级同步」小节。

## 验收标准（阶段 3 达成标志，对齐 plan.md）

- [x] 多租户权限系统：登录 + 三档角色 + 403 矩阵（K2/K3 单测 + live 探针）
- [x] 检索 ACL：密级白名单过滤 + PATCH 即时生效（K4 单测 + live：viewer 0 hit → PATCH → 1 hit）
- [x] 审计日志：写路径全覆盖、可查询（K1 单测 + live：HTTP 上传/PATCH/登录均落库）
- [x] 全量门禁：pytest **318 passed**（新增 **31** 单测：K1×7 + K2×12 + K3×4 + K4×8）、ruff/black/mypy/tsc 全绿、真栈集成 1 passed（`RAGIMS_INTEGRATION=1`）、K6 E2E 探针 exit 0

## 产出物（K6 完成）

| 位置 | 内容 |
| :-- | :-- |
| `tests/test_k_integration.py` | 真栈集成：HTTP 登录 → 进程内上传 → PATCH 密级 → viewer 不可见 → 改回可见 → viewer 403 矩阵 → 审计行校验 → 篡改 token 401（marker-gated） |
| `scripts/_k6e2e_tmp.py` | 全 HTTP 双用户探针（8 步，exit 0 验收通过；临时文件待删） |
| `docs/api.md` | + 认证（/auth/login、/auth/me）、审计（/audit-logs）、检索 ACL 说明 |
| `docs/runbook.md` | + §4.5 认证与密级（密码回填 / 强制登录开关 / 401·403 排查 / 密级同步失败处置） |
| `docs/db-schema.md` | + §3.10 audit_logs DDL；延后清单移除 audit_logs |

## 关联任务

- 汇总 [K1](k1-audit-logs.md)、[K2](k2-auth-login.md)、[K3](k3-roles-permissions.md)、[K4](k4-search-acl.md)、[K5](k5-frontend-auth.md)。
