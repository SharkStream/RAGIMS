# MVP4 · 阶段 4 质量与评估

> 依据 [plan.md 阶段 4](../../plan.md)（质量检查/重复检测 · 检索测试/评估指标 · 人工审核 → 质量看板 + 评估报告）与 §4.8 表设计（`evaluation_runs` / `quality_checks`）。
> 阶段 3（K 权限与多租户）已完成；阶段 4 在其之上（所有 API 继承登录/角色/审计/租户隔离）。

## 任务卡

| 任务 | 文件 | 说明 | 状态 |
| :-- | :--- | :-- | :-- |
| L1 | [l1-quality-schema.md](l1-quality-schema.md) | `quality_checks` + `evaluation_runs` 两表（迁移 0005）+ ORM 模型 | ✅ |
| L2 | [l2-quality-checks.md](l2-quality-checks.md) | 三项内置质量检查（空块率/重复率/长度分布）接入流水线 + 文档质量 API | ✅ |
| L3 | [l3-evaluation-engine.md](l3-evaluation-engine.md) | 评估引擎：数据集 → 批量检索 → recall@k / MRR / nDCG@k，评估报告落库 + API | ✅ |
| L4 | [l4-quality-frontend.md](l4-quality-frontend.md) | 质量看板页：文档质量结果 + 发起评估 + 报告视图 + 人工审核 | ✅ |
| L5 | [l5-tests-acceptance.md](l5-tests-acceptance.md) | 收官：单测/真栈集成/探针 + 文档全套更新 | ✅ |

**依赖**：L1 → L2 → L3 → L4 → L5（关键路径 L1 → L2 → L3）。

## 阶段达成标志（对齐 plan.md 交付物）

- 质量看板：任何文档版本可查三项质量检查得分；低分可人工标注
- 评估报告：给定查询-期望文档数据集，一键跑出 recall@k / MRR / nDCG@k 并留存历史
- 门禁：pytest（阶段 3 基线 331 passed 之上新增）+ ruff/black/mypy/tsc 全绿 + live 探针
