# C4 · 阶段 C 验收标准

> **阶段**：C 文档上传与元数据 API　**依赖**：C1、C2、C3

## 验收清单

- [x] 上传 PDF/DOCX/TXT 均成功落库 + 落 MinIO。
- [x] 上传后能查到 `documents`、`document_versions`、`ingestion_jobs` 记录。
- [x] 重复上传相同文件触发幂等逻辑。
- [x] 接口有 Pydantic schema 校验与错误码。

## 验收记录（2026-10-22，远程 MySQL / MinIO / Redis，完整重演）

1. **三类型全链**（C1 只验过 txt，本次补齐 PDF/DOCX）：最小合法签名的 `%PDF-1.4` / `PK\x03\x04` docx / txt 各经 HTTP multipart 上传 → 201 + 三表行齐（`file_type` 归一、`file_size` 正确、job `pending`）+ MinIO 对象字节回读一致。
2. **幂等**：PDF 重传 → `duplicate=true`、返回同一 `doc_id`，全库 (documents, versions, jobs) 行数不变。
3. **错误码矩阵**：`.exe` → 415；MIME 伪造（pdf 文件报 text/html）→ 415；超限 → 413；数据源 `type=s3` → 501 `ERR_NOT_IMPLEMENTED`；数据源重名 → 409；未知文档 → 404 —— 全部统一 envelope。
4. **读侧闭环**：列表含全部三文档；详情带 `latest_version`。
5. 质量门禁：ruff / black / mypy（45 文件）零错误，pytest **109 passed**（C1 10 + C2 9 + C3 6 个离线用例）。

## 达成标志

文档上传与元数据读写闭环，为 D–F 流水线提供数据入口。**阶段 C 完成** ✅

## 关联任务

- 上游：[C1](c1-upload-api.md)、[C2](c2-document-query-api.md)、[C3](c3-datasource-api.md)。
- 下游：[D 解析清洗切分](d1-parser-abstraction.md)、[F 流水线](f1-celery-base.md)。
