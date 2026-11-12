# N3 · 生成质量评估（LLM-as-judge）

> **阶段**：N 优化与扩展　**依赖**：[N1](n1-chat-api.md)（被评估对象）、[L3](../mvp4/l3-evaluation-engine.md)（评估引擎扩展点）　**工时**：约 1 天

## 目标

评估报告从「检索质量」单维升级为「**检索质量 + 生成质量**」双维：faithfulness（忠实度，答案是否只依据上下文）与 answer relevancy（答案与问题的相关性）。

## 技术选型

- **不引入 RAGAS**（重依赖 + LLM 调用链黑盒）——自实现两个指标，judge 用 N1 的 chat_client（LLM-as-judge，结构化 JSON 输出），与项目零依赖哲学一致。
- 指标定义（各 0-1）：
  - **faithfulness**：把答案拆成原子断言 → 逐条判定「能否由给定上下文支撑」→ 支撑比例。低分 = 幻觉。
  - **answer_relevancy**：judge 对 (query, answer) 打相关分 + 判定「是否拒答/答非所问」。拒答且上下文确实不足 = 合理拒答（不罚分，单列 `refusal` 标记）。

## 实施步骤

1. `evaluation_runs.kind` 字段（迁移 0007 与 N2 合并或独立）：`retrieval`（默认，存量兼容）/ `generation`。
2. generation 数据集条目：`{query, expected_doc_ids?, reference_answer?}`（reference 可选——有则额外算答案-参考相似性参考分）。
3. 执行器：逐条调 **chat API 内部函数**（非 HTTP）→ 拿 (answer, citations, context) → 两次 judge 调用（faithfulness / relevancy，温度 0，JSON 输出 + 解析失败重试 1 次）→ 落 `metrics{faithfulness, answer_relevancy, refusal_rate}` + 逐条 breakdown（含 judge 理由）。
4. **审计**：`eval.run`（沿用）；judge 的 token 消耗单独记日志（成本可见）。
5. 前端：评估报告按 kind 渲染（generation 报告显示 faithfulness/relevancy 指标卡 + judge 理由列）。

## 验收标准

- [ ] 同一数据集跑 generation 评估：faithfulness / relevancy 指标产出且人工抽查 judge 理由合理
- [ ] 拒答用例被正确归类（refusal_rate 统计而非罚分）
- [ ] 存量 retrieval 评估完全兼容（kind 默认值）
- [ ] 门禁全绿 + live 探针

## 关联任务

- N1（被测对象）、N2（检索模式对比可叠加生成指标）。
