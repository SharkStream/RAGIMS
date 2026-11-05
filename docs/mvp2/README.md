# MVP2（阶段 2 · 版本与增量）任务索引

> 对应 `plan.md` 八/阶段 2「版本与增量（3-4 周）」。阶段代号 **J**，接续 MVP1 的 I 阶段。
> 文档风格沿用 [docs/mvp1/](../mvp1/README.md)：每任务一个文件，目标 / 现状 / 实施步骤 / 验收标准 / 关联任务。
>
> **状态：✅ 全部完成（J1–J6）**——单测 287 passed、真栈集成 3 passed、live 探针 8 项全过、门禁全绿。

## 与 MVP1 的衔接：已有什么、缺什么

阶段 2 四个任务的现状盘点（截至 MVP1 完成）：

| plan.md 阶段 2 任务 | MVP1 现状 | 缺口 → 承接任务 |
| :-- | :-- | :-- |
| content_hash、版本表 | ✅ 已有：`document_versions` 表（`UNIQUE(doc_id, content_hash)`、`is_latest`、`file_path` 含版本段、`chunk_count/embedding_model`） | 无需建表 |
| 增量更新 | ❌ **上传 version 硬编码 1**：同名不同 hash 会另建新文档（新 doc_id），不会产生 v2 | **J1** |
| 软删除 | ✅ 已有：文档级软删（status=deleted，检索过滤）；版本级删除没有 | J4 附带 |
| 回滚 | ❌ 无版本切换/激活 API，Qdrant `is_latest` 写死 `true` | **J4** |
| 重新处理 | ✅ 已有：`POST /documents/{id}/reprocess`（复用 latest 版本重建 job） | 无需改 |
| 元数据变更不重嵌入 | ❌ 无任何元数据更新 API（title/tags/access_level 建后不可改） | **J3** |
| 版本切换逻辑 | ❌ 无版本列表/详情 API，前端无版本视图 | **J2 + J5** |

**核心设计决策（各任务共同遵守）：**

1. **增量 = 追加新版本，不删旧版本**：同 `(tenant, file_name)` 不同 `content_hash` 上传 → 新 `DocumentVersion`（version=N+1），旧版本 chunk 行与 Qdrant 点**全部保留**，仅 `is_latest` 翻转——回滚因此是零成本的（数据都在，只改指针）。
2. **回滚/切换 = 翻转指针，不重算**：激活旧版本只做三件事——MySQL `is_latest`/`current_version` 翻转、Qdrant `set_payload` 批量翻转 `is_latest`、文档 `updated_at` 刷新。**不重新解析、不重新嵌入、不重新上传对象**（`file_path` 天然带版本段 `{tenant}/{doc_id}/{version}/{file_name}`，旧版本对象一直在 MinIO）。
3. **元数据变更永不进队列**：PATCH 只 UPDATE `documents` 行，不产生 job、不碰 chunk/向量。
4. **检索零改动**：检索强制 `is_latest=true` 过滤（MVP1 已实现），切换版本后自动生效，无需动 search_service。

## 阶段 J · 版本与增量（预估 2.5-3.5 天）

| 任务 | 文件 | 说明 | 状态 |
| :--- | :--- | :--- | :-- |
| J1 | [增量上传（版本递增）](j1-incremental-upload.md) | 同名不同内容 → vN+1；幂等与冲突语义 | ✅ |
| J2 | [版本查询 API](j2-version-api.md) | 版本列表 / 版本详情 + chunks | ✅ |
| J3 | [元数据更新 API](j3-metadata-update.md) | PATCH title/tags/access_level，不重嵌入 | ✅ |
| J4 | [版本切换与回滚](j4-version-switch.md) | activate 旧版本；Qdrant payload 翻转；版本级软删 | ✅ |
| J5 | [前端版本视图](j5-frontend-version-ui.md) | 版本历史抽屉 Tab、切换/回滚按钮、元数据编辑 | ✅ |
| J6 | [测试与验收](j6-tests-acceptance.md) | 单测 + 真栈集成 + 阶段验收 | ✅ |

**依赖**：J1 → J2（列表要能展示多版本）→ J4（切换）；J3 独立可并行；J5 依赖 J2/J3/J4 的 API；J6 收尾。关键路径 **J1 → J2 → J4 → J6**。

## 交付物（达成标志）

- ✅ 同一文档名重复上传不同内容 → 版本线性递增（v1→v2→…），检索始终命中 latest
- ✅ 任意历史版本可一键回滚（秒级，零重嵌入），回滚后检索/下载/chunk 预览全部指向回滚版本
- ✅ title/tags/access_level 可更新且不触发任何任务队列
- ✅ 前端可查看完整版本历史并执行切换
- ✅ `scripts/reconcile.py` 版本漂移对账兜底（runbook §3）
