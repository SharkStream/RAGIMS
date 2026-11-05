# J4 · 版本切换与回滚（含版本级软删）

> **阶段**：J 版本与增量　**依赖**：J1、J2　**工时**：约 1 天

## 目标

把任意历史版本**激活**为 latest（= 回滚）：MySQL 指针翻转 + Qdrant payload 批量翻转，**零解析、零嵌入、零对象操作**，检索/下载/chunk 预览立即指向回滚版本。附带版本级软删除（回收单版本 chunk+点+对象）。

## 现状（MVP1 行为，需改）

- `document_versions.is_latest` 只有「新版插入时翻转」一条路径；
- Qdrant payload `is_latest: True` **写死**（`vectoring_service.build_payload`）——切换版本后若不更新 payload，检索过滤 `is_latest=true` 会同时命中新旧版本或全不命中；
- chunk 预览/下载走 `current_version`，缺切换入口。

## 实施步骤

1. `POST /api/documents/{doc_id}/versions/{version:int}/activate` → `DocumentDetail`：
   - 校验：目标版本存在、`parse_status == 'parsed'`（未完成版本不可激活 → 409）、非当前 latest（幂等：已 latest → 200 原样返回）；
   - MySQL 事务内：旧 latest `is_latest=False`；目标 `is_latest=True`；`doc.current_version = version`；`doc.status = 'succeeded'`（历史版本已解析完毕）；
   - Qdrant：`set_payload` 两次——
     a) `filter{doc_id, is_latest=true}` → `{"is_latest": false}`（先把现 latest 点降级）
     b) `filter{doc_id, version=目标}` → `{"is_latest": true}`；
     两次都按 `tenant_id` 复合过滤（租户安全）。顺序：先降后升，中间窗口检索短暂为空可接受（秒级）。
2. **一致性兜底**：payload 翻转失败（Qdrant 宕机）→ MySQL 事务**不提交**（同一 try 块），返回 503 `ERR_UNAVAILABLE`；对账脚本 `reconcile.py` 增加规则：`documents.current_version` vs Qdrant `is_latest` 点集不一致时报告（复用现有对账框架）。
3. `DELETE /api/documents/{doc_id}/versions/{version:int}`（版本级软删，**不可删当前 latest** → 409）：
   - 删该版本 chunk 行 + `delete_points_by_filter{doc_id, version}` + MinIO 对象（raw + parsed-text）；`deleted_versions` 无表——直接物理删（MVP2 决策：版本级只有"回收"，无"回收站"）；整文档软删（现有）保持不变。
4. 回滚语义即 activate（不单设 rollback 端点，文档写明等价关系）。
5. 上传路径补齐：新版本 job 失败时**保持旧 latest 可用**——J1 已保证（旧版本 is_latest 翻转发生在 job 成功前？**否**：J1 在上传时就把旧版本置 false、新版本置 true——**决策**：上传即切换 latest（新版本是「当前」），失败可 reprocess 或回滚；文档化该语义于本文件「已知取舍」）。

## 已知取舍（写进代码注释与本文档）

- 上传 vN+1 即刻抢占 latest：嵌入失败期间检索为空/旧内容不可见 → 用「上传后立刻 cancel/reprocess」缓解；若需「成功才切换」，把翻转挪进 `finish_job`（改动大，MVP2 不做）。
- activate 的 Qdrant 双 set_payload 非原子：以先降后升序保证「不会双版本命中」。

## 验收标准

- [x] v2 上传成功 → activate v1：`current_version=1`、v1 `is_latest=true`、检索命中 v1 内容（点 payload 已翻转）、chunk 预览/下载指向 v1
- [x] activate 后再次 activate 同版本 → 200 幂等
- [x] 未解析版本 activate → 409；跨租户 → 404
- [x] Qdrant 停机时 activate → 503 且 MySQL 未变（重启后可重试）
- [x] 版本级 DELETE：非 latest 可删（chunk/点/对象消失）；latest → 409
- [x] 对账脚本能发现 MySQL 与 Qdrant 的 is_latest 漂移
- [x] 单测 + 真栈集成（v1→v2→切回 v1 全链）

## 产出物（J4 完成）

| 位置 | 内容 |
| :-- | :-- |
| `app/api/documents.py` | `POST /documents/{id}/versions/{version}/activate`（幂等）+ `DELETE /documents/{id}/versions/{version}`（物理回收） |
| `app/services/document_service.py` | `activate_document_version`：MySQL 指针翻转 **flush 后**才做 Qdrant 双 set_payload（先降后升，租户复合过滤），Qdrant 失败 → 整体 rollback + 503 `ERR_UNAVAILABLE`；`delete_document_version`：chunk 行 + job_steps/ingestion_jobs（FK 链）+ Qdrant 点 + MinIO raw/parsed 对象，latest → 409 |
| `app/services/vectoring_service.py` | **latest 收敛修复**：`build_payload` 的 `is_latest` 改取 `version.is_latest`（原写死 true）；`upsert_doc_vectors` 在 latest 版本 upsert 前先 demote 该 doc 旧 latest 点——上传抢占 latest 的 MySQL 语义从此与 Qdrant 时序无关地收敛 |
| `app/clients/qdrant_client.py` + `storage.py` | `set_payload_by_filter` / `scroll_points`（协议 + 实现双层） |
| `scripts/reconcile.py` + `consistency.py` | 新对账规则 `find_is_latest_drift`：MySQL `current_version` vs Qdrant `is_latest=true` 点集逐文档比对，漂移报告（不自动修复） |

## 验收证据（live 探针 real exit 0）

| # | 场景 | 结果 |
| :- | :--- | :--- |
| 1 | 回滚前检索 | 命中 v2 内容 ✓ |
| 2 | activate v1 | MySQL 翻转 + **检索立即命中 v1 内容**（payload 已翻转） |
| 3 | 幂等再 activate | 200，指针不变 |
| 4 | latest chunk 端点 | 指向 v1 |
| 5 | Qdrant 停机（stub） | 503 + MySQL 指针原样 |
| 6 | 版本级删除 v2 | chunk/点/对象/jobs 全回收，points == chunks |
| 7 | 删 latest | 409 `ERR_CONFLICT` |
| 8 | reconcile | `is_latest pointers aligned`（回滚后无漂移） |

## 已知取舍（实现时确认/新增）

- 上传 vN+1 即刻抢占 latest：Qdrant 旧点 demote 在上传事务后 best-effort 执行 + 流水线 upsert 前强制收敛（见 vectoring_service），失败由对账规则兜底报告。
- activate 的双 set_payload 非原子：先降后升保证「不会双版本命中」，秒级检索空窗可接受。
- 版本级删除同时回收该版本的 job 痕迹（ingestion_jobs/doc_version_id 是 FK，无回收站表）。

## 关联任务

- 依赖 [J1](j1-incremental-upload.md)、[J2](j2-version-api.md)；前端 [J5](j5-frontend-version-ui.md)；对账复用 [E4](../mvp1/e4-consistency.md)。
