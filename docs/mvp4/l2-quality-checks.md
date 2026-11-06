# L2 · 流水线质量检查

> **阶段**：L 质量与评估　**依赖**：[L1](l1-quality-schema.md)　**工时**：约 0.5 天
> 对应 plan.md 6.2 流水线第 11 步「质量检查：抽样、重复率、空块检测」。

## 目标

每次摄取完成后自动给文档版本打质量分，供质量看板（L4）与后续切分调优使用。

## 实施步骤（完成 ✅）

1. `app/services/quality_service.py` 三检查器（score = **风险占比，越低越好**，归一 [0,1]，原始计数进 detail）：

   | check_type | 算法 | detail |
   | :-- | :-- | :-- |
   | `empty_ratio` | 去空白后 <20 字符的 chunk 占比 | chunks / empty / min_chars |
   | `duplicate_ratio` | 归一化（去空白+小写）后重复 chunk 行数占比 | chunks / duplicates / unique |
   | `length_spread` | chunk 长度变异系数 CV（=std/mean，封顶 1.0） | chunks / mean / cv |

2. `run_quality_checks(session, doc_version_id)`：读版本全部 chunk 文本 → 三检查 →
   **删旧插新**（reprocess 幂等）→ 提交；`best_effort_quality_checks` 包装器吞异常只告警。
3. worker 接入（[pipeline.py](../../backend/app/workers/pipeline.py)）：`finalize_version`
   之后、`finish_job` 之前调用 best-effort 版——**检查崩溃绝不影响摄取任务成功**。
4. 读侧 API：`GET /api/documents/{doc_id}/quality`（登录即可读）→
   `list_document_quality`（service，join document_versions 取版本序号，新版本在前），
   响应 `QualityCheckOut[]`。

## 验收标准

- [x] 纯函数单测 7 例（风险占比、归一化、CV 封顶）
- [x] DB 行为单测（重跑覆盖式替换：1 次 delete + 3 行 insert）
- [x] API 单测（版本分组倒序、viewer 可读、空列表）
- [x] worker 韧性单测（checker 崩溃不冒泡）
- [x] 门禁：pytest **342 passed**、ruff/black/mypy 全绿

## 关联任务

- 数据层 [L1](l1-quality-schema.md)；看板 [L4](l4-quality-frontend.md)。
