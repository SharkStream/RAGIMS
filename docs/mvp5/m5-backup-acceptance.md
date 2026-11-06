# M5 · 备份恢复与验收（阶段 5 收官）

> **阶段**：M 可观测与运维　**依赖**：M1-M4　**工时**：约 0.5 天

## 验收标准（对齐 plan.md 交付物）

- [x] 监控大盘：第六页「监控」——健康卡（依赖探活+告警+gauge，30s 刷新）+ token 成本条形表
- [x] 指标抓取：`/api/metrics` Prometheus 格式（live 24 条序列）
- [x] 备份恢复：`scripts/backup.py` 零依赖 dump（live：mysql.sql 86KB / MinIO 对象 / MANIFEST）+ runbook §7 恢复步骤
- [x] 门禁：pytest **365 passed**、ruff（app/tests/scripts）/ black / mypy / tsc 全绿

## 产出物（M5 完成）

| 位置 | 内容 |
| :-- | :-- |
| `scripts/backup.py` | 备份：MySQL（python INSERT dump 默认 / mysqldump 可选）+ MinIO 两桶对象 + MANIFEST.json |
| `docs/runbook.md` | + §7 备份与恢复（含恢复五步）；常用命令补 alert_check / cleanup / metrics |
| `docs/api.md` | + 监控（/api/metrics）与成本（/stats/costs） |
| `README.md`（根） | 阶段 5 ✅ + 第六页「监控」 |

## 关联任务

- 汇总 [M1](m1-metrics.md)、[M2](m2-cost.md)、[M3](m3-alerts.md)、[M4](m4-dashboard.md)。
