# M1 · 指标采集

> **阶段**：M 可观测与运维　**依赖**：无　**工时**：约 0.5 天

## 目标

`GET /api/metrics` 输出 Prometheus 文本格式（**零新依赖**，手写 exposition），
可供 Prometheus / 任意抓取器直接采集。

## 实施步骤（完成 ✅）

1. `app/core/metrics.py`：进程内线程安全注册表——
   `ragims_http_requests_total{method,route,status}`、
   `ragims_http_request_duration_seconds_{sum,count}{method,route}`、
   `ragims_process_uptime_seconds`；`route_template` 取 `scope["route"].path`
   模板（**低基数**，不含具体 doc_id）。
2. `app/main.py` HTTP middleware：计时 + 计数，异常绝不影响请求。
3. `app/api/metrics.py`：每次抓取时从 DB 派生 gauge——
   文档（按 status）/ 版本 / chunks / 质量检查行 / 评估次数 / 用户 /
   任务（按 status）+ **队列深度**（pending+running）/ **embedding tokens 累计** /
   各流水线步骤平均耗时（timestampdiff 微秒聚合）。
4. 挂载 `/api/metrics`（**按惯例不鉴权**：仅聚合统计无业务载荷；AUTH_REQUIRED=true
   时业务接口 401 而抓取端点保持可读）。

## 验收标准

- [x] 单测 5 例：计数累积 / exposition 格式 / 路由模板低基数 / middleware 真实计数 / DB gauge 标签
- [x] **真实 DB 回归捕获**：步骤耗时聚合缺 GROUP BY（MySQL 1140 only_full_group_by）→ 修复
- [x] 门禁：pytest **361 passed**、ruff/black/mypy 全绿
- [x] live：`/api/metrics` 200，18 条序列（HTTP 计数 + 全部派生 gauge）

## 关联任务

- 成本统计 [M2](m2-cost.md)（tokens 指标共用数据源）、告警 [M3](m3-alerts.md)。
