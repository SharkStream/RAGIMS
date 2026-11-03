# G4 · 阶段 G 验收标准

> **阶段**：G 任务 / Chunk / 检索测试 API　**依赖**：G1–G3

## 验收清单

- [x] 检索测试能返回相关 chunk，score 合理。
- [x] 跨租户数据不可见。
- [x] 任务列表与步骤可视化数据完整。

## 验收证据（G4 综合探针，真栈，real exit 0）

| # | 清单项 | 实测 |
| :- | :--- | :--- |
| 1 | 检索相关 + score 合理 | "cloud migration schedule" → 命中目标文档，top score=**0.4832**，分项耗时 `embed=1056.4ms / search=386.7ms` |
| 2 | 跨租户不可见 | 异租户检索 → **0 hits**；恶意 filters（伪造 tenant_id/is_latest/is_deleted）→ 仍 0 hits |
| 3 | 任务数据完整 | `GET /jobs?doc_id=` 命中 + 7 步全有 `duration_ms` 与 output |

达成标志 ✅：后端 API 能力完整（documents / chunks / jobs / search / stats 五组接口），为 H 前端提供全部数据接口。

## 关联任务

- 上游：[G1](g1-job-api.md)、[G2](g2-search-test.md)、[G3](g3-stats.md)。
- 下游：[H 前端管理界面](h1-frontend-init.md)。
