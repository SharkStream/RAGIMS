# J6 · 测试与验收（阶段 2 收官）

> **阶段**：J 版本与增量　**依赖**：J1-J5　**工时**：约 0.5-1 天

## 目标

版本与增量能力的自动化验证 + 阶段验收，风格同 [I1/I2/I4](../mvp1/i1-automated-tests.md)。

## 实施步骤

1. **单测**（offline）：
   - J1：三分支（新 doc / duplicate / 新版本）+ 并发同 hash（线程 + 真锁语义 or mock 锁）+ 软删文档同名新建；
   - J2：列表/详情/404/租户隔离/分页；
   - J3：PATCH 成功/422/409/404 + **零 job 断言**；
   - J4：activate 翻转（含幂等/未解析 409/Qdrant 失败回滚 503 mock）/latest 删除 409。
2. **真栈集成**（`tests/test_j_integration.py`，marker-gated 同 I1）：
   - `test_incremental_upload_and_versions`：txt 上传 v1 → 改内容传 v2 → 版本行/MinIO 对象/current_version 断言；
   - `test_activate_rollback_full_cycle`：v1→v2 检索命中 v2 → activate v1 → 检索命中 v1 + payload is_latest 校验 → 重新 activate v2；
   - `test_metadata_patch_no_reembed`：PATCH 后 job 数不变；
   - cleanup fixture 同 I1 零残留（含两版本点/对象）。
3. **验收探针**（`scripts/_j6e2e_tmp.py`）：J1→J2→J3→J4 全链 live 走查（real exit 0），含检索切换验证。
4. **文档收尾**：`docs/mvp2/README.md` 勾交付物、todolist.md 阶段 J 全勾、api.md 补新端点（versions/activate/PATCH）、runbook 补「版本漂移对账」小节。

## 验收标准（阶段 2 达成标志，对齐 plan.md）

- [ ] 版本化文档管理：同名递增版本、历史可查可预览
- [ ] 增量更新能力：新版本上传零手工干预、旧版本数据完整保留
- [ ] 回滚秒级生效且检索同步（payload 一致性有对账兜底）
- [ ] 元数据变更零重嵌入（job 数恒定可证）
- [ ] 全量门禁：pytest（新增 ≥20 用例）、ruff/black/mypy、tsc、真栈集成全绿

## 关联任务

- 汇总 [J1](j1-incremental-upload.md)、[J2](j2-version-api.md)、[J3](j3-metadata-update.md)、[J4](j4-version-switch.md)、[J5](j5-frontend-version-ui.md)。
