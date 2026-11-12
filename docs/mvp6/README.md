# MVP6 · 阶段 6 优化与扩展（第一批：RAG 完整化）

> 依据 [plan.md 阶段 6](../../plan.md)（持续迭代）与 2026-11 差距分析：**系统缺 RAG 的「G」（生成）与检索增强的高级形态**——这是平台能力与面试叙事的最大缺口。
> 前五个阶段已完成（摄取/版本/权限/质量评估/可观测）；本阶段在其之上补全闭环。

## 任务卡

| 任务 | 文件 | 说明 | 状态 |
| :-- | :--- | :-- | :-- |
| N1 | [n1-chat-api.md](n1-chat-api.md) | **Chat API**：SSE 流式生成 + 引用溯源 + 拒答策略（把 RAG 的 G 补上） | ⬜ |
| N2 | [n2-hybrid-rerank.md](n2-hybrid-rerank.md) | **混合检索**（Qdrant sparse+dense RRF 融合）+ LLM rerank + 用评估引擎跑 ablation 对比报告 | ⬜ |
| N3 | [n3-generation-eval.md](n3-generation-eval.md) | **生成质量评估**：faithfulness / answer relevancy（LLM-as-judge，零依赖自实现）接入评估引擎 | ⬜ |
| N4 | [n4-guardrails.md](n4-guardrails.md) | Guardrails：prompt injection 防护 + PII 脱敏 + per-user 速率限制（Redis 计数） | ⬜ |
| N5 | [n5-tracing-notify.md](n5-tracing-notify.md) | OpenTelemetry 全链路 tracing（可选依赖+开关）+ 告警 webhook 通知 + 收官 | ⬜ |

**依赖**：N1 → N2 → N3 → N4 → N5（N1 是后续一切的地基；N2/N3 构成 ablation 闭环）。

## 本阶段达成标志

- 用户在前端提问 → 流式获得**带 chunk 引用**的回答；上下文不足时明确拒答
- 同一评估数据集产出 **dense vs hybrid vs hybrid+rerank** 的 recall@k / nDCG@k 对比报告（数据说话的优化故事）
- 评估报告同时覆盖**检索质量 + 生成质量**双维指标
- 恶意文档注入 / 敏感信息 / 滥用调用均有防护与记录

## 设计基调（延续既有约定）

- 零重依赖优先（RAGAS/SlowAPI 等自实现替代）；新依赖必须可开关（OTel）
- 所有新检索能力尊重四条件强制过滤（tenant + is_latest + is_deleted + 密级白名单）
- 每卡：单测 + 门禁 + live 验证；收官跑探针
