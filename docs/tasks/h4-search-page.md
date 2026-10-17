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

- [ ] 检索返回结果并展示 score/来源/页码。
- [ ] 展示分项耗时。

## 关联任务

- 依赖 [H1](h1-frontend-init.md)、[G2](g2-search-test.md)。
