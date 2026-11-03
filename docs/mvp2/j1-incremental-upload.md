# J1 · 增量上传（版本递增）

> **阶段**：J 版本与增量　**依赖**：MVP1（C1 上传链路）　**工时**：约 1 天

## 目标

同一文档名（同 tenant + `file_name`）上传**不同内容**时，产生该文档的**新版本**（vN+1），而不是另建新文档；上传**相同内容**仍走幂等（duplicate=true，不产生新版本）。

## 现状（MVP1 行为，需改）

`app/services/document_service.py`：

- `upload_document` 里 `DocumentVersion(version=1)`、`Document(current_version=1)` **硬编码**（约 247/252 行）；
- `_find_duplicate` 只匹配「同名 + 同 hash」→ 命中返回 duplicate；同名**不同 hash** 会落进全新创建分支 → **第二个 doc**（版本管理失效）。

## 实施步骤

1. `_find_version_head(session, tenant_id, file_name)`：查同名文档（`status != 'deleted'`）的最新文档行 + 其 `current_version`（没有则 None）。
2. `upload_document` 分支重构：
   - 无同名文档 → 现行为（新 doc，version=1）；
   - 同名 + 同 hash（latest 版本）→ 现行为（duplicate=true，复用版本）；
   - 同名 + 不同 hash → **追加版本**：`version = current_version + 1`；新 `DocumentVersion(version=N, is_latest=True)`；旧 latest 版本 `is_latest=False`；`doc.current_version = N`；`doc.status = 'processing'`（重新进入流水线）；MinIO 对象路径已含版本段，不会覆盖旧对象。
3. 并发竞态收口（I2 已知限制的彻底修复）：对「同名查重→插入」路径加 **MySQL 行锁**（`SELECT ... FOR UPDATE` 于 documents 行）或 `file_name` 唯一化事务重试；同名同 hash 并发双传 → 一次新版本 + 一次 duplicate。
4. 新版本 job 仍走现有 `full` 流水线（`doc_version_id` 指向新版本）——旧版本 chunk/点不动。
5. 响应 `UploadResponse` 增加 `version`（已有）与语义确认：duplicate=false 时 version=N。

## 验收标准

- [ ] 同名 v1 上传 → v2 上传：一个 doc、两个 version 行、v1 `is_latest=false`、`current_version=2`
- [ ] v1 与 v2 的 MinIO 对象同时存在（路径含 `/1/`、`/2/`）
- [ ] 同内容重复上传 v2 → duplicate=true，版本数不变
- [ ] 并发同 hash 双传：恰好 1 个新版本 + 1 个 duplicate（I2 竞态关闭）
- [ ] 软删文档同名上传 → 新文档（不受 deleted 行影响）
- [ ] 单测覆盖三分支 + 并发；真栈集成验证

## 关联任务

- 依赖 [C1](../mvp1/c1-upload-api.md)；被 [J2](j2-version-api.md)、[J4](j4-version-switch.md) 消费。
