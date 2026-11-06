# L3 · 评估引擎

> **阶段**：L 质量与评估　**依赖**：[L1](l1-quality-schema.md)　**工时**：约 1 天
> 交付物「评估报告」的计算与留存核心。

## 目标

给定查询-期望文档数据集，用**与 `/search/test` 完全相同的检索路径**（强制租户 +
is_latest + ACL 过滤，基准视角 admin 覆盖全部密级）批量执行，产出经典排序指标并落库，
支持历史对比与逐条人工审核。

## 实施步骤（完成 ✅）

1. `app/services/evaluation_service.py`：
   - `single_query_metrics(hit_doc_ids, expected, top_k)`：recall@k / 交叉秩 RR /
     nDCG@k（二值相关）/ first_hit_rank，手算例锁定（rank2 命中 → RR=0.5、
     nDCG≈0.6309；k 截断外不记分）。
   - `run_evaluation(session, run, top_k)`：逐条跑 `search_test` → 聚合
     `{queries, top_k, recall@k, mrr, ndcg@k, hit_rate}` + 逐条 breakdown
     `result`；`create_and_run_evaluation` 一站式建行 + 执行 + 提交。
2. `app/api/evaluations.py` + 挂载 `/api/evaluations`：
   - `POST /evaluations`：同步跑（数据集 ≤100 条），**审计 `eval.run`**（detail:
     name/queries/top_k/recall@k）
   - `GET /evaluations`：本租户历史（倒序，摘要级）；`GET /evaluations/{id}`：完整报告
   - 跨租户读取 → 404（K7 同款语义）
3. `app/schemas/evaluation.py`：数据集校验（query 非空 ≤512、expected 1-20 个
   doc_id、条数 1-100、top_k 1-20）。

## 验收标准

- [x] 指标单测 5 例（完美/未命中/次席/部分召回/k 截断）
- [x] 运行器单测（聚合口径、admin 视角、断言逐条 result）
- [x] API 单测（201+审计、422 校验矩阵、跨租户 404）
- [x] 门禁：pytest **352 passed**、ruff/black/mypy 全绿
- [x] live 冒烟并入 [L5](l5-tests-acceptance.md) 探针（真实索引上 recall=1.0 验证）

## 关联任务

- 数据层 [L1](l1-quality-schema.md)；看板 [L4](l4-quality-frontend.md)；收官 [L5](l5-tests-acceptance.md)。
