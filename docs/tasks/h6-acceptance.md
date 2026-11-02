# H6 · 阶段 H 验收标准

> **阶段**：H 前端管理界面　**依赖**：H1–H5

## 验收清单

- [x] 上传 → 看任务进度 → 看 chunk → 检索测试 全链路可在 UI 完成。
- [x] 错误提示友好（上传失败、任务失败、检索无结果）。
- [x] 响应式基本可用（桌面优先）。

## 达成标志

四类页面可用，支撑 M3「前端可用」里程碑（第 4-5 周）。✅ **H 阶段收官**

## H6 验收记录

**增强**（验收驱动的小改）：

- `src/api/client.ts` — 错误码 → 中文友好文案映射（`ERR_FILE_TYPE_NOT_ALLOWED`/`ERR_NOT_FOUND`/`ERR_NETWORK` 等 8 个），页面 toast 不再裸露英文报错；
- `documents.tsx` / `jobs.tsx` — 详情抽屉宽度自适应（`min(640/680, innerWidth-32)`），窄屏不出横向溢出。

**全链路 live 探针**（real exit 0，复刻四页的全部调用）：

| # | 场景 | 结果 |
| :- | :--- | :--- |
| 1 | 上传 .exe（H2 前端校验兜底） | 415 `ERR_FILE_TYPE_NOT_ALLOWED`，友好文案映射 ✓ |
| 2 | 上传 txt → 任务进度（7 步）→ chunk 预览 | job succeeded，2 chunks 列出 ✓ |
| 3 | 检索命中 + doc_id 过滤空态 | 3 hits / 0 hit（Empty 渲染数据）✓ |
| 4 | 设置页数据 | 默认模型 + 切分参数可见 ✓ |
| 5 | 重试按钮守卫 | succeeded job retry → 409（UI 本就不显示按钮）✓ |

前端 `tsc --noEmit` 零错误。

**浏览器手动走查清单**（`pnpm dev` 后，http://localhost:5173）：

1. 「文档」：拖拽 txt → 进度条 → 列表出现新行（状态「处理中」）；
2. 「任务」：轮询 5s 内状态翻转「成功」→ 详情抽屉七步时间线全绿；
3. 「文档」：详情抽屉 → Chunk 预览分页；
4. 「检索测试」：输入原文关键词 → 命中 + 耗时卡片；清空过滤条件改查无词 → 空态；
5. 「设置」：默认模型与切分参数卡片。

## 关联任务

- 上游：[H1](h1-frontend-init.md)–[H5](h5-settings-page.md)。
- 下游：[I 测试、联调、验收](i1-automated-tests.md)。
