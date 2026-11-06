# MVP5 · 阶段 5 可观测与运维

> 依据 [plan.md 阶段 5](../../plan.md)（日志/指标/告警 · 任务监控/成本统计 · 备份恢复 → 监控大盘 + 运维手册）。
> 阶段 4（L 质量与评估）已完成；结构化日志（loguru JSON）与 job_steps 逐步耗时已在前序阶段就绪。

## 任务卡

| 任务 | 文件 | 说明 | 状态 |
| :-- | :--- | :-- | :-- |
| M1 | [m1-metrics.md](m1-metrics.md) | Prometheus 指标：HTTP 计数/耗时 + 任务/文档/成本派生指标（/api/metrics，零新依赖） | ✅ |
| M2 | [m2-cost.md](m2-cost.md) | 成本统计：embedding token 消耗聚合 API（按天/按模型） | ✅ |
| M3 | [m3-alerts.md](m3-alerts.md) | 健康详情 + 告警检查脚本（失败率/积压/依赖探活，可挂 cron） | ✅ |
| M4 | [m4-dashboard.md](m4-dashboard.md) | 监控大盘前端：健康卡 + 任务趋势 + 成本曲线 | ✅ |
| M5 | [m5-backup-acceptance.md](m5-backup-acceptance.md) | 备份恢复脚本（mysqldump + MinIO）+ 验收 + 文档收官 | ✅ |

**依赖**：M1 → M2 → M3 → M4 → M5（M2/M3 可并行）。

## 阶段达成标志（对齐 plan.md 交付物）

- 监控大盘：系统健康 / 任务成功率与耗时 / token 成本一页可见
- 指标可供 Prometheus 抓取；告警脚本可定时检查失败率与积压
- 备份恢复有可执行脚本与 runbook 步骤
- 门禁全绿 + live 探针
