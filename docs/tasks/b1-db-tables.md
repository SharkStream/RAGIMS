# B1 · 数据库表（MVP 子集）

> **阶段**：B 数据模型与存储层（2-3 天）　**依赖**：A　**工时**：约 0.5 天

## 目标

确定 MVP 必需的 9 张表及其字段，作为 B2 ORM 建模的输入。**只建这 9 张**，`plan.md` 第四节标注「延后」的 6 张（`chunking_strategies`、`parsers`、`permissions`、`audit_logs`、`evaluation_runs`、`quality_checks`）**不建**。

## 9 张表与关键字段

> 完整定义见 `plan.md` 第四节；通用约定：主键 `id UUID CHAR(36)`、`created_at`/`updated_at` 时间戳、MySQL 8 用 `JSON`（非 `JSONB`）。

1. **tenants**（MVP 预置一条默认租户）：`id`、`name`、`status`、`created_at`、`updated_at`
2. **users**（MVP 预置默认管理员）：`id`、`tenant_id`、`username`、`email`、`role`、`status`、`created_at`、`updated_at`
3. **datasources**（MVP 只实现 `local`）：`id`、`tenant_id`、`name`、`type`、`config JSON`、`sync_mode`、`sync_cron`、`last_sync_at`、`status`、`created_at`、`updated_at`
4. **embedding_models**（预置 OpenAI `text-embedding-3-small` 默认配置）：`id`、`name`、`provider`、`model_name`、`dimension`、`config JSON`、`is_default`
5. **documents**：`id`、`tenant_id`、`datasource_id`、`external_id`、`title`、`file_name`、`file_type`、`url`、`author`、`department`、`document_type`、`access_level`、`tags JSON`、`current_version`、`status`、`created_at`、`updated_at`
6. **document_versions**：`id`、`doc_id`、`version`、`content_hash`、`file_path`、`file_size`、`parse_status`、`chunk_count`、`embedding_model`、`is_latest`、`is_deleted`、`valid_from`、`valid_to`、`created_at`、`updated_at`
7. **chunks**：`id`、`doc_version_id`、`doc_id`、`version`、`chunk_index`、`text`、`token_count`、`chunk_hash`、`page`、`section`、`qdrant_point_id`、`metadata JSON`、`created_at`
8. **ingestion_jobs**：`id`、`tenant_id`、`doc_id`、`doc_version_id`、`job_type`、`status`、`priority`、`created_by`、`celery_task_id`、`created_at`、`started_at`、`finished_at`、`error_message`
9. **job_steps**：`id`、`job_id`、`step_order`、`step_name`、`status`、`retry_count`、`input JSON`、`output JSON`、`started_at`、`finished_at`、`error_message`

## 相对 plan.md 第四节的字段补充（本次已回写）

- `ingestion_jobs` 增加 `celery_task_id`（阶段 F retry/cancel 关联队列任务）。
- `job_steps` 增加 `step_order`（步骤排序，避免依赖时间戳）。
- `tenants`/`users`/`datasources` 补 `updated_at`。

## 验收标准

- [ ] 9 张表字段清单与 `plan.md` 第四节一致，延后 6 张已排除。
- [ ] 字段类型已按 MySQL 语义（`JSON`、`CHAR(36)`、`DATETIME`）明确。

## 关联任务

- 输入给 [B2 ORM 与迁移](b2-orm-migration.md)；下游 [C1 上传接口](c1-upload-api.md) 依赖表结构。
