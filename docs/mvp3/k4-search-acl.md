# K4 · 检索 ACL 与密级同步

> **阶段**：K 权限与多租户　**依赖**：K2、K3　**工时**：约 0.5-1 天

## 目标

检索按「角色密级白名单」过滤；PATCH 密级立即对检索生效（补 J3 遗留）。

## 现状

- 检索硬过滤 tenant + is_latest + is_deleted；**payload 里的 access_level 未消费**——viewer 能检索到 confidential 内容。
- `PATCH access_level` 只改 MySQL——Qdrant 点 payload 的 access_level 不同步（改回 internal 也不会重新可见）。

## 实施步骤

1. 白名单：`admin/editor → {public, internal, confidential}`；`viewer → {public, internal}`（常量进 `app/core/permissions.py`）。
2. `search_service.search()`（生产检索）与 `search_test`：`_mandatory_filter` 追加 `access_level ∈ 白名单`（`qmodels.Filter` 的 should/must_terms）。
3. **密级同步**：`update_document_meta` 当 `access_level` 变更时，对该文档**全部版本**的点 `set_payload_by_filter({"access_level": new})`（flush 后、commit 前，失败 503 同 J4 模式）；版本切换/删除路径无需改（payload 继承自点创建时）。
4. 上传/流水线不变（build_payload 已带 access_level）。
5. 单测：viewer 检索不见 confidential；editor 可见；PATCH 密级 confidential→internal 后 viewer 立即可见（点已同步）；sync 失败 503 且 MySQL 回滚。

## 验收标准

- [x] viewer 检索结果不含 confidential 文档（`/search/test` 消费端 + 硬过滤）
- [x] PATCH access_level 后检索立即生效（无需 reprocess）
- [x] 同步失败 → 503 + MySQL 未变（J4 同款 flush → payload → commit 模式）

## 产出物（K4 完成）

| 位置 | 内容 |
| :-- | :-- |
| `app/core/permissions.py` | `ACCESS_LEVELS_BY_ROLE`（K3 预置，K4 消费；未知角色降级 viewer 白名单） |
| `app/services/search_service.py` | `_mandatory_filter` 第 4 条硬过滤：`access_level ∈ MatchAny(白名单)`；请求 `access_level` 只能**收窄**白名单（交集为空 → 结构性空结果，不触 Qdrant）；`search_test(role=...)` |
| `app/api/search.py` | 端点透传 `user.role` |
| `app/services/document_service.py` | `update_document_meta`：level 变更时对该文档**全部版本**点 `set_payload_by_filter`（未变更不触发；Qdrant 挂 → rollback + 503 `ERR_UNAVAILABLE`） |
| `tests/test_k4_acl.py` | 8 个单测（白名单矩阵 / 收窄不放大 / 空交集零查询 / 全版本同步 / 未变跳过 / 失败 503 回滚） |
| `tests/test_g2_search.py` | 安全断言升级为 K4 语义（4 条强制条件，白名单可见） |

## 验收证据（live，real）

| # | 场景 | 结果 |
| :- | :--- | :--- |
| 1 | 机密文档（confidential）上传 + 就绪 | ✓ |
| 2 | admin 检索命中 | 1 hit |
| 3 | viewer（真 DB 行）检索同一查询 | **0 hit（隔离生效）** |
| 4 | PATCH 回 internal → viewer 立即命中 | **1 hit（同步生效，无需 reprocess）** |

门禁：pytest **318 passed**（+8）· ruff / black / mypy 全绿。

## 关联任务

- 依赖 [K2](k2-auth-login.md)、[K3](k3-roles-permissions.md)；修复 J3 遗留（j3-metadata-update.md 已知取舍）。
