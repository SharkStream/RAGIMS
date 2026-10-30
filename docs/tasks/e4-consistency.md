# E4 · 一致性保障

> **阶段**：E Embedding + Qdrant 入库（3-4 天）　**依赖**：E2、E3　**工时**：约 0.5 天

## 目标

保证幂等与可对账：重复处理不产生重复 points，缺失 point_id 的记录可重试。

## 实施步骤

### 1. 幂等
- 相同 `doc_version_id` 重复处理时，先按 filter（`doc_version_id`）删除旧 points，再 upsert。

### 2. 对账脚本（MVP 简易版）`backend/scripts/reconcile.py`
- 扫描 `chunks` 缺失 `qdrant_point_id` 的记录并重试回写。

## 验收标准

- [x] 相同文档重复处理不产生重复 points。
- [x] 对账脚本能发现并修复缺失 point_id 的记录。

## 产出物（E4 完成，E 阶段收官）

- `app/services/consistency.py` — `purge_version_points`（按 `doc_version_id` filter **删旧再写**——比纯覆盖更强：重处理时 chunk 数减少也不残留旧点位）；`find_missing_point_ids`（扫描 `chunks.qdrant_point_id IS NULL`）；`repair_missing_point_ids`（两级修复：**回填型**——Qdrant 里点位已存在（payload `chunk_index` 匹配），零成本回填 ID；**重嵌入型**——点位缺失则重新 embed + upsert + 回填）。
- `scripts/reconcile.py` — 对账 CLI：扫描 → 修复 → 复扫，输出报告；幂等可重复执行（干净状态 exit 0 "nothing to do"）。
- `tests/test_e4_consistency.py` — 5 个离线用例（filter 目标字段、purge 调用参数、回填型不触发重嵌入、重嵌入型走 mock upsert、无缺失 no-op）。

## 实现说明

- **两级修复设计**：point id 由 `point_id_for` 确定性可算，但「点位是否真在 Qdrant」需查——修复时先 filter-only 检索（dummy vector + `doc_version_id` filter）建 `chunk_index → point_id` 映射：命中的行直接回填（F 流水线「upsert 成功但回写失败」的典型场景零成本修复），未命中的才重新 embed。
- **live E2E**（真库 + 真 Qdrant + 真实 API）：2 chunks 全链 → 模拟部分回写失败（1/2 缺 point_id）→ repair `backfilled=1, reembedded=0`（零成本回填 ✓）→ purge 2 点 → 重新 upsert → 2 points（无重复 ✓）→ `scripts/reconcile.py` 实跑 "nothing to do" exit 0。
- 质量门禁：ruff（含 scripts）/black/mypy（59 文件）零错误，pytest **206 passed**。

## 关联任务

- 依赖 [E2](e2-qdrant-write.md)、[E3](e3-mysql-metadata.md)。
