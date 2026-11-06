# L5 · 测试与验收（阶段 4 收官）

> **阶段**：L 质量与评估　**依赖**：L1-L4　**工时**：约 0.5 天

## 验收标准（对齐 plan.md 交付物）

- [x] 质量看板：文档版本级三项检查得分可查（live：empty/duplicate/length_spread 全落库）
- [x] 评估报告：live 数据集基准 recall@k=1.0 / MRR=1.0 / nDCG@k=1.0 / hit_rate=1.0，历史+逐条报告可查，人工审核 verdict 落库
- [x] 门禁：pytest **354 passed**（阶段新增 **23** 单测：L2×11 + L3×12 + B2 扩展）、ruff/black/mypy/tsc 全绿、L5 E2E 探针 8 步 exit 0

## 产出物（L5 完成）

| 位置 | 内容 |
| :-- | :-- |
| `scripts/_l5e2e_tmp.py` | 全链探针：上传 → 流水线（含质量检查）→ 质量 API → 评估（全 1.0）→ 历史/报告 → 审核 → 审计 → 自清理 |
| `docs/api.md` | + 质量检查（/documents/{id}/quality）与评估（/evaluations CRUD + review） |
| `docs/db-schema.md` | + §3.11/3.12 两表 DDL；延后清单移除 quality_checks/evaluation_runs |
| `README.md`（根） | 阶段 4 ✅ + 第五页「质量与评估」 |
| [plan.md](../../plan.md) | 阶段 4 标记完成 |

## 探针修正记录（实施中发现并修复）

1. **质量检查未落库**：worker 把 ORM `version` 对象传给 `run_quality_checks`，
   `session.get(...)` 主键误用 → 改传 `version.id` + service 侧防御性 `getattr(id)`。
2. **评估文档级排名**：同文档多 chunk 命中会占据 top-k 多席压低 recall →
   `run_evaluation` 按文档去重（保留首现顺序）后再算指标。

## 关联任务

- 汇总 [L1](l1-quality-schema.md)、[L2](l2-quality-checks.md)、[L3](l3-evaluation-engine.md)、[L4](l4-quality-frontend.md)。
