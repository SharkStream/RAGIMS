# C4 · 阶段 C 验收标准

> **阶段**：C 文档上传与元数据 API　**依赖**：C1、C2、C3

## 验收清单

- [ ] 上传 PDF/DOCX/TXT 均成功落库 + 落 MinIO。
- [ ] 上传后能查到 `documents`、`document_versions`、`ingestion_jobs` 记录。
- [ ] 重复上传相同文件触发幂等逻辑。
- [ ] 接口有 Pydantic schema 校验与错误码。

## 达成标志

文档上传与元数据读写闭环，为 D–F 流水线提供数据入口。

## 关联任务

- 上游：[C1](c1-upload-api.md)、[C2](c2-document-query-api.md)、[C3](c3-datasource-api.md)。
- 下游：[D 解析清洗切分](d1-parser-abstraction.md)、[F 流水线](f1-celery-base.md)。
