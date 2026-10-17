# D2 · 各格式解析器

> **阶段**：D 解析、清洗、切分（4-5 天）　**依赖**：D1、B3　**工时**：约 1.5 天

## 目标

实现 PDF / DOCX / TXT 三种解析器，解析结果统一落 MinIO，失败状态回写。

## 实施步骤

### 1. PDF `backend/app/parsers/pdf_parser.py`
- 用 `pymupdf`（优先，`fitz`）提取文本 + 页码 + 基本元数据（标题/作者）。
- 逐页产出 `Block`（`page` 编号准确）。

### 2. DOCX `backend/app/parsers/docx_parser.py`
- 用 `python-docx` 提取段落 + 表格；表格转 markdown/纯文本。

### 3. TXT `backend/app/parsers/txt_parser.py`
- 直接读取，`chardet` 编码探测后 decode。

### 4. 结果落 MinIO
- 复用 [B3](b3-storage-layer.md) 的 `StorageService`：解析结果写 `parsed-text/{doc_version_id}.json`。

### 5. 失败回写
- 解析失败：`document_versions.parse_status=failed`，`job_steps.error_message` 记录堆栈摘要（由 F 流水线统一处理）。

## 验收标准

- [ ] 三种格式样例均能产出非空 `ParsedDocument`。
- [ ] 解析结果落 MinIO 可回读。
- [ ] 解析失败可正确落库并可见错误信息。

## 关联任务

- 依赖 [D1](d1-parser-abstraction.md)、[B3](b3-storage-layer.md)；被 [D3 清洗](d3-cleaning.md) 使用。
