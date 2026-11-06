# M3 · 告警

> **阶段**：M 可观测与运维　**依赖**：[M1](m1-metrics.md)　**工时**：约 0.5 天

## 目标

健康详情一站可见 + 可定时执行的告警检查（阈值退出码，接入任意调度/通知）。

## 实施步骤（完成 ✅）

1. `GET /health/detail`（根路径，无包络，HTTP 恒 200——判断看 JSON）：
   - `checks`：MySQL / Redis / Qdrant 探活（复用 readyz 探针 + 耗时）
   - `gauges`：documents_total / queue_depth（pending+running+retrying）/
     jobs_failed_24h / jobs_settled_24h
   - `alerts`：阈值判定（队列 > 50；24h 失败率 > 0.3 且样本 ≥5；DB 不可达），
     全部通过 → `status=ok`，否则 `degraded`
2. `scripts/alert_check.py`：独立脚本（不依赖 API 在跑）——依赖探活 + 同款阈值；
   退出码 **0 健康 / 1 告警 / 2 自身错误**；`--json` 供日志采集；`--max-queue /
   --max-failure-rate / --min-sample` 可调；live 实测 `status=ok`。

## 验收标准

- [x] live：`/health/detail` 200 + `status=ok` + gauges 正确
- [x] live：`alert_check.py` exit 0（探活全绿 + 无告警），`--json` 可解析
- [x] 门禁：pytest **365 passed**、ruff（app/tests/scripts）/ black 全绿

## 关联任务

- [M1](m1-metrics.md)（指标口径一致）、[M4](m4-dashboard.md)（大盘健康卡）。
