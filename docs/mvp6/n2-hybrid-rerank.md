# N2 · 混合检索 + Rerank + Ablation

> **阶段**：N 优化与扩展　**依赖**：[N1](n1-chat-api.md)（chat 消费检索）、[L3](../mvp4/l3-evaluation-engine.md)（ablation 基建）　**工时**：2-3 天

## 目标

解决「向量检索召回不准」的标准三件套：**混合检索**（词法+语义融合）、**rerank 重排**、以及用**自家评估引擎跑 ablation** 证明收益——数据说话的优化故事。

## 技术选型（关键取舍）

- **混合检索用 Qdrant 原生 sparse+dense**，不引入 OpenSearch/ES：
  - 上传时为每 chunk 计算 **sparse 向量**（词频 BM25 风格：token → 维度 hash，值 = tf-idf 权重；纯 Python 实现）
  - 检索时 query 同样生成 sparse 向量 → `prefetch`（dense + sparse）→ Qdrant **RRF 融合**（`fusion=rrf`）
  - 零新服务、零新依赖；强项：型号名/编号/专有名词等词法命中（dense 弱项）
- **Rerank 用 LLM pointwise**（OpenAI 兼容 chat 对 top-N 逐条打相关分 0-10，结构化输出），不用 cross-encoder（避免 torch/sentence-transformers 重依赖）；可配置关闭。

## 实施步骤

1. **配置**：`RETRIEVAL__MODE`（dense / hybrid，默认 dense 渐进）、`RETRIEVAL__RERANK`（bool，默认 off）、`RETRIEVAL__RERANK_TOP_N`（默认 20）。
2. **sparse 向量**：`app/services/sparse_service.py`（tokenize → hash 维度（如 65536）→ tf 权重 → Qdrant named vector `sparse`；`SparseVector(indices, values)`）。
3. **写入侧**：upsert 时同时写 dense + sparse named vectors（Qdrant collection 需重建/迁移——**migration 脚本**：scroll 旧点重写，或重建 collection + reprocess 引导，写清取舍）。
4. **读侧**：`search_service` 按 `RETRIEVAL__MODE` 构造 prefetch 查询（dense limit=k、sparse limit=k → RRF 融合 top-k）；四条件强制过滤不变。
5. **rerank**：N1 的 chat_client 对 top-N 打分重排；失败降级为不重排（best-effort）。
6. **Ablation 报告**：`evaluation_runs` 增加 `retrieval_mode` 字段（迁移 0007）；同一数据集跑 dense / hybrid / hybrid+rerank 三组 → `docs/mvp6/ablation.md` 记录对比数据与结论。

## 验收标准

- [ ] hybrid 模式：专有名词查询（dense 0 命中的样例）能召回
- [ ] rerank：top-k 内相关文档排名上升（用评估数据集量化）
- [ ] ablation 表：三模式 × recall@5 / MRR / nDCG@5 完整对比
- [ ] 旧数据迁移路径验证；门禁全绿；live 探针

## 关联任务

- N1（chat 直接受益）、N3（generation 评估基于检索结果）。
