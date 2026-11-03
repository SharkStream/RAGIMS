# H4 · 检索测试页

> **阶段**：H 前端管理界面（5-6 天）　**依赖**：H1、G2　**工时**：约 1 天

## 目标

实现检索测试交互页面。

## 实施步骤

### 1. 页面 `frontend/src/pages/Search/index.tsx`
- 输入 query、top_k、可选过滤条件。
- 结果列表：score、文本片段、来源文档、页码。
- 展示 embedding/search 耗时。

## 验收标准

- [x] 检索返回结果并展示 score/来源/页码。
- [x] 展示分项耗时。

## 产出物（H4 完成）

- `src/pages/search-test.tsx` — 检索测试页：
  - **输入**：query TextArea（Enter 提交）+ `top_k` InputNumber（1–20）+ 可选 `doc_id` 过滤（G2 白名单 filters）；
  - **结果**：List 逐条 `score`（4 位小数，volcano Tag）/ 来源 `doc_id`（截断 Tag）/ 版本 v / `第 N 页` Tag / `chunk #index` Tag + 原文段落；空态 `无命中结果`；
  - **分项耗时**：三个 Statistic（Embedding / 向量检索 / 总耗时，ms）+ 命中数 `n / top_k`。

## 验收证据（live，真后端 + worker，real exit 0）

| # | 场景 | 实测 |
| :- | :--- | :--- |
| 1 | 上传含标记语的 txt → 全链 | job succeeded |
| 2 | `POST /search/test`（query=标记语, top_k=5） | **3 hits**，score=0.6274，来源 doc_id 正确；embed=908ms / search=134ms / total=1042ms |
| 3 | top_k=1 + doc_id 命中/未命中 | 1 hit / 0 hit，页面两种渲染路径 |

前端 `tsc --noEmit` 零错误。浏览器侧请 `pnpm dev` → 「检索测试」页实际体验。

## 关联任务

- 依赖 [H1](h1-frontend-init.md)、[G2](g2-search-test.md)。
