# L4 · 质量看板前端

> **阶段**：L 质量与评估　**依赖**：[L2](l2-quality-checks.md)、[L3](l3-evaluation-engine.md)　**工时**：约 1 天
> 交付物「质量看板」+ plan.md 阶段 4 第三项「人工审核」。

## 目标

新「质量与评估」页（第五个导航页）：文档质量分查询 + 评估发起/历史/报告 + 结果级人工审核。

## 实施步骤（完成 ✅）

1. [quality.tsx](../../frontend/src/pages/quality.tsx) 两块：
   - **文档质量**：输入 doc_id → 版本倒序检查表（空块率/重复率/长度离散 +
     风险配色：<0.1 绿 / <0.3 橙 / ≥0.3 红 + 原始计数 detail）
   - **检索评估**：历史表（recall@k/MRR/nDCG@k/hit_rate 速览）→ 新建评估
     Modal（名称 + top_k + 数据集 JSON 粘贴，前端解析校验）→ 报告 Drawer
     （四个指标卡 + 逐条查询命中明细）
2. **人工审核**（L3 `PATCH /evaluations/{id}/results/{index}` + `eval.review` 审计）：
   报告逐条行内 Select（✓ 正确 / ✗ 误检 / △ 漏检）→ 即时回写 `result[i].review`。
3. `App.tsx`：菜单第五项「质量与评估」（`/quality`，RequireAuth 包裹）；
   `api/index.ts`：`qualityApi`（byDocument / listEvaluations / evaluation /
   runEvaluation / reviewResult）+ 类型。

## 验收标准

- [x] `tsc --noEmit` 0 错误
- [x] 后端 review 端点单测 2 例（verdict 回写 + 越界 400 / 非法值 422 + `eval.review` 审计）
- [x] 门禁：pytest **354 passed**、ruff/black/mypy 全绿

## 收尾增强（用户反馈闭环）

- **报告展示评估集**：Drawer 增加「评估集（本次输入）」区块（查询 + 期望命中文档），
  修复「输入内容不可见」的展示遗漏（数据本就在 `evaluation_runs.dataset` 中返回）。
- **编辑并重跑（方案 A）**：报告 Drawer 头部「编辑并重跑（生成新评估）」→
  以原 run 预填表单 → 修改后提交生成一条新 run——老报告不可变，新旧并排可对比。
- **重跑溯源（L4.1，迁移 0006）**：废弃 `-rerun` 名字后缀（嵌套重跑名字膨胀），
  `evaluation_runs` 新增 `parent_run_id` 软指针（**故意无 FK**，run 可独立清理）：
  重跑沿用原名 + 记录派生来源，历史表与报告标题显示「↻ 重跑」徽标，
  审计 detail 带 `parent_run_id`；跨租户 parent → 404。

## 关联任务

- [L2](l2-quality-checks.md)（质量数据）、[L3](l3-evaluation-engine.md)（评估 API）。
