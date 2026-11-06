# M4 · 监控大盘前端

> **阶段**：M 可观测与运维　**依赖**：[M2](m2-cost.md)、[M3](m3-alerts.md)　**工时**：约 0.5 天

## 目标

交付物「监控大盘」：第六导航页 `/monitoring`，运维一页可见。

## 实施步骤（完成 ✅）

1. [monitoring.tsx](../../frontend/src/pages/monitoring.tsx)：
   - **健康卡**：总体状态徽标（ok/degraded）+ 依赖探活行（MySQL/Redis/Qdrant ✓/✗ + 耗时）
     + 四个 gauge（文档/队列积压/24h 失败/24h 完成）+ 告警 Tag；**30s 自动刷新**
   - **Token 成本卡**：累计 tokens / embed 调用次数 / 有消耗天数 + 按日条形表（纯 CSS 条形，零图表依赖）
2. `/api/health/detail` 双挂载（根路径供 LB 探针 + `/api` 前缀供前端 axios）。
3. `api/index.ts`：`opsApi`（healthDetail / costs）+ `HealthDetail` / `CostSummary` 类型。

## 验收标准

- [x] `tsc --noEmit` 0 错误
- [x] live：`/api/health/detail` 200（前端路径可达）+ `/stats/costs` 200
- [x] 后端门禁保持全绿（365 passed）

## 关联任务

- [M3](m3-alerts.md)（数据源）、[M5](m5-backup-acceptance.md)（收官）。
