# J5 · 前端版本视图（版本历史 / 回滚 / 元数据编辑）

> **阶段**：J 版本与增量　**依赖**：J2、J3、J4　**工时**：约 1 天

## 目标

文档详情抽屉升级为多 Tab：**概要（现有）/ 版本历史 / Chunk 预览（现有）**；版本历史 Tab 提供切换（回滚）操作；概要 Tab 提供元数据编辑。

## 现状（H2 文档页，需改）

`frontend/src/pages/documents.tsx`：详情抽屉单视图（字段 + chunks 预览 + 重处理/软删按钮）；无版本概念展示。

## 实施步骤

1. `src/api/index.ts` 新增类型化方法：
   - `documentVersionsApi.list(docId, page, pageSize)` → J2 列表
   - `documentVersionsApi.activate(docId, version)` → J4
   - `documentVersionsApi.remove(docId, version)` → J4 版本级删
   - `documentsApi.patch(docId, patch)` → J3
   - `DocumentVersionOut` / `DocumentPatch` 类型（与后端 schema 对齐）
2. 详情抽屉改 `Tabs`（沿用 H3 抽屉宽度 `min(680, innerWidth-32)`）：
   - **概要**：现有字段 + 「编辑元数据」按钮 → Modal 表单（title/tags（Select tags 模式）/access_level），提交 PATCH，成功 message + 刷新；
   - **版本历史**：`Table`（version/latest Tag/hash 前 12/chunk_count/parse_status/created_at + 行操作「设为当前」「删除版本」（latest 行禁用两个操作））；分页接 J2；操作需 `Popconfirm`；activate 成功后刷新抽屉 + 外层列表（status 变 succeeded）；
   - **Chunks**：现有预览逻辑迁入（数据源不变）。
3. 状态标签复用 `statusTag`（succeeded 已在 H 修复时支持）。
4. 错误处理走现有 `errorMessage()`（409 冲突/404 均有友好文案映射，必要时补 `ERR_CONFLICT` 文案）。

## 验收标准

- [x] 版本历史 Tab 列出全部版本、latest 高亮（「当前」Tag）、倒序、分页正常
- [x] 「设为当前」→ 成功提示 + 版本表/外层列表刷新 + 检索命中回滚版本（J4 live 已验证检索即时切换；前端接同一 API）
- [x] latest 行的「设为当前/删除版本」禁用；两操作均有 Popconfirm 防误触
- [x] 元数据编辑：title/tags/access_level 保存后详情+列表即时更新；live 验证任务看板**无新 job**（jobs.total 不变）
- [x] `tsc --noEmit` 零错误（`pnpm build` 因开发机 node_modules 缺 rollup 原生包未能跑，需在正常终端执行）

## 产出物（J5 完成）

| 位置 | 内容 |
| :-- | :-- |
| `frontend/src/api/index.ts` | `DocumentVersionOut`（补 chunk_count/embedding_model）、`DocumentPatch`、`documentsApi.patch`、`documentVersionsApi.{list,activate,remove}` |
| `frontend/src/pages/documents.tsx` | 详情抽屉改 3 Tab（概要/版本历史/Chunks）：概要加「编辑元数据」Modal（title/tags-Select-tags/access_level）；版本历史 Table（version+当前 Tag、哈希前 12 可复制、chunk_count、parse_status、大小、时间 + 行操作） |
| `backend/app/schemas/document.py` + `api/documents.py` | `DocumentOut` 补 `access_level` / `tags`（前端编辑表单数据源） |

## live 验证证据（HTTP 冒烟，5/5）

| # | 场景 | 结果 |
| :- | :--- | :--- |
| 1 | 详情返回 `access_level` / `tags` | ✓ |
| 2 | PATCH title+tags+access_level → 200 全生效 | ✓ |
| 3 | 列表 keyword 查新标题命中、tags 同步 | ✓ |
| 4 | 版本列表含 chunk_count | ✓ |
| 5 | PATCH 后 `/jobs?doc_id` 仍只有 1 个 job（零新 job） | ✓ |

质量门禁：后端 pytest 287 passed / ruff / black / mypy 全绿；前端 `tsc --noEmit` 0 错误。

## 关联任务

- 依赖 [J2](j2-version-api.md)、[J3](j3-metadata-update.md)、[J4](j4-version-switch.md)；承接 [H2](../mvp1/h2-document-page.md) 文档页。
