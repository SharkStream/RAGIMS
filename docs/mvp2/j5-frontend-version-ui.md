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

- [ ] 版本历史 Tab 列出全部版本、latest 高亮、倒序、分页正常
- [ ] 「设为当前」→ 成功提示 + 列表刷新 + 检索测试页验证命中回滚版本内容
- [ ] latest 行的「设为当前/删除版本」禁用；确认弹窗防误触
- [ ] 元数据编辑：title/tags 修改保存后列表/详情即时更新；任务看板**无新 job**
- [ ] tsc --noEmit 零错误；`pnpm build` 通过

## 关联任务

- 依赖 [J2](j2-version-api.md)、[J3](j3-metadata-update.md)、[J4](j4-version-switch.md)；承接 [H2](../mvp1/h2-document-page.md) 文档页。
