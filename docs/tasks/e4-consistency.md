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

- [ ] 相同文档重复处理不产生重复 points。
- [ ] 对账脚本能发现并修复缺失 point_id 的记录。

## 关联任务

- 依赖 [E2](e2-qdrant-write.md)、[E3](e3-mysql-metadata.md)。
