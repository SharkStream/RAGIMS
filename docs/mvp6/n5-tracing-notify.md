# N5 · OpenTelemetry Tracing + 告警通知 + 收官

> **阶段**：N 优化与扩展　**依赖**：N1-N4　**工时**：约 1 天

## 目标

全链路追踪（一条 chat 请求跨 API → Celery → LLM 的完整链路）与告警通知闭环，阶段收官。

## 实施步骤

1. **OpenTelemetry（可选依赖 + 总开关）**：
   - 依赖：`opentelemetry-sdk / -api / -instrumentation-fastapi / -instrumentation-celery / -instrumentation-sqlalchemy / -exporter-otlp`（安装为 **extras**：`pip install -e .[otel]` 或 requirements-otel.txt——**默认不装**，`OTEL__ENABLED=false` 时零开销零导入）
   - `app/core/tracing.py`：`setup_tracing()`（OTLP exporter，`OTEL__ENDPOINT` 配置）；main.py / celery_app.py 各一行接入
   - 自定义 span：`chat.generation`（含 model/tokens 属性）、`retrieval.search`（mode/top_k/hits）
   - 验证：本地启 Jaeger all-in-one（docker）看链路
2. **告警通知**：`alert_check.py` 加 `--webhook <URL>`（通用 POST JSON：status/alerts/gauges，兼容钉钉/企微/Slack 简单格式）+ `--quiet-ok`（健康时不发）；告警文案含主机名与时间戳。
3. **收官**：N1-N5 探针（chat 流式 + ablation 数据 + 注入/限流用例 + trace 导出）+ 文档全套（api.md / runbook / README / plan 勾选）。

## 验收标准

- [ ] `OTEL__ENABLED=true` 时 Jaeger 可见完整 chat 链路（HTTP → retrieval → LLM span 树）；false 时行为与开销零变化
- [ ] alert_check 告警时 webhook 收到 JSON（curl 接收验证）
- [ ] 门禁全绿 + 探针 exit 0 + 文档收官

## 关联任务

- N1-N4（收官汇总）。
