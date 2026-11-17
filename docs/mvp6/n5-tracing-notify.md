# N5 · Tracing + 告警通知 + 收官

> **阶段**：N 优化与扩展　**依赖**：N1-N4　**工时**：约 1 天

## 目标

全链路追踪（chat 请求跨 API → 检索 → LLM）与告警通知闭环，阶段 6 第一批收官。

## 实施步骤（完成 ✅）

1. **OpenTelemetry（可选依赖 + 总开关）**：
   - 依赖隔离在 [requirements-otel.txt](../../backend/requirements-otel.txt)（**默认不装**）；
   - [tracing.py](../../backend/app/core/tracing.py)：`setup_tracing()`（OTLP HTTP exporter）；
     `OTEL__ENABLED=false`（默认）时**不导入任何 otel 包、零开销**，`trace_span()` 退化为 `_NullSpan`；
   - 接线：`main.py`（FastAPI auto-instrumentation + SQLAlchemy）、`celery_app.py`（Celery）、
     `chat_service.build_chat_contexts`（自定义 span `ragims.chat.retrieval`）+
     `chat.stream()`（`ragims.chat.generation`，含 model/contexts 属性）；
   - 失败降级：bundle 缺失/端点错误只 warning，不影响启动。
2. **告警通知**：`alert_check.py` 加 `--webhook <URL>`（通用 JSON POST）+ `--always`
   （健康心跳模式）；通知失败不计入检查结果（非致命）。
3. **收官**：门禁 + live 探针 + 文档全套。

## 验收标准

- [x] 关闭时零开销（`_NullSpan` 单测覆盖 `set_attribute`/`record_exception`）
- [x] 开启时 provider/instrumentor 装配 + span 树 live 捕获（`ragims.chat.retrieval`，属性 top_k/role 正确）
- [x] bundle 缺失降级不炸启动（单测）
- [x] `--webhook` live 收到 JSON（status/gauges/alerts 字段完整）；健康时默认不发、`--always` 发
- [x] 门禁：pytest **400 passed**、ruff / black / mypy（100 files）全绿

## 阶段 6 第一批收官汇总

| 任务 | 关键产出 | 量化结论 |
| :-: | :-- | :-- |
| N1 | Chat API（SSE + 引用 + 拒答）+ 对话页 | 端到端回答带 `[n]` 溯源 |
| N2 | hybrid（sparse+dense RRF）+ rerank + ablation | **词法 recall@5 0.625 → 0.9375（+50%）** |
| N3 | faithfulness / relevancy / refusal_rate | 双维评估落库，拒答单列 |
| N4 | 注入三层防护 + PII + Redis 限流 | 429 + 降级放行 |
| N5 | OTel（可选）+ webhook 告警 | span 树 live 可捕获 |

## 关联任务

- 收官汇总 N1-N4；后续候补（语义切分/父子块、多模态、数据源连接器、embedding 缓存）见 plan 阶段 6 说明。
