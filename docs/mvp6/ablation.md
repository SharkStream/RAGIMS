# N2 · Ablation 报告：dense vs hybrid vs hybrid_rerank

> 数据：`D:\Projects\RAGIMS\test\docs`（27 个中文知识文档，561 chunks，全部 named-vector 写入）
> 评估器：RAGIMS 自建评估引擎（L3 + N2 mode 参数）；`top_k=5`；文档级去重排名

## 实验一 · 标题型查询（query = 文档首句，27 条）

query 与文档内容语义高度重合——dense 的舒适区。

| 模式 | recall@5 | MRR | nDCG@5 | hit_rate |
| :-- | :-: | :-: | :-: | :-: |
| dense | 1.0 | 1.0 | 1.0 | 1.0 |
| hybrid | 1.0 | 1.0 | 1.0 | 1.0 |
| hybrid_rerank | 1.0 | 0.9815 | 0.9863 | 1.0 |

**结论**：天花板效应——easy case 三种模式都满分；hybrid 无损。rerank 出现轻微波动（LLM judge 在已完美的排序上偶发 1 位换序），佐证「rerank 应可配置关闭」（`RETRIEVAL__RERANK=false` 默认）。

## 实验二 · 词法挑战查询（query = 文档内精确编号/缩写，16 条）

提取各文档中的特定 token（IELTS / B2C / AICPA / K8s / PEP8 / 批准书编号…）作为 query——**dense 语义向量的已知弱项**（缩写/编号缺乏语义信号）。

| 模式 | recall@5 | MRR | nDCG@5 | hit_rate |
| :-- | :-: | :-: | :-: | :-: |
| dense | **0.625** | 0.4688 | 0.5097 | 0.625 |
| hybrid | **0.9375** | **0.7969** | **0.8327** | **0.9375** |

**结论**：hybrid 相对 dense **recall@5 +50%（0.625 → 0.9375）**，MRR +70%——词法稀疏向量把「精确 token 命中」补齐了。这正是混合检索存在的理由。

## 综合结论

1. **hybrid 无损于语义查询、大幅改善词法查询** → 建议生产默认 `RETRIEVAL__MODE=hybrid`（成本：写入时多算 sparse；查询时多一路 prefetch）。
2. **rerank 保持默认关闭**：在 easy case 上引入波动；应在「难以直接判断」的真实生产语料上另行测量其收益与延迟（+1 次 LLM 往返）。
3. 评估集应包含**词法挑战用例**——只测语义近似的用例会让 dense 看起来「完美」而掩盖真实短板（本实验一即是例证）。

## 复现

```powershell
# collection 升级（dense 单向量 → dense+sparse，零重嵌入）
env\Scripts\python.exe scripts\migrate_hybrid.py
# 评估（qualityApi 或 curl）：retrieval_mode = dense | hybrid | hybrid_rerank
POST /api/evaluations {"name":"ablation-hybrid","retrieval_mode":"hybrid","top_k":5,"dataset":[...]}
```
