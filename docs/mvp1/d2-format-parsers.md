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

- [x] 三种格式样例均能产出非空 `ParsedDocument`。
- [x] 解析结果落 MinIO 可回读。
- [x] 解析失败可正确落库并可见错误信息。

## 产出物（D2 完成）

- `app/parsers/pdf_parser.py` — `PdfParser`：PyMuPDF（新 import 名 `pymupdf`）逐页提取（`load_page` + `get_text`），每非空页一个 `Block`（页码 1-based），`metadata` 收 title/author 等并滤空值。
- `app/parsers/docx_parser.py` — `DocxParser`：按 `body.iterchildren()` **文档顺序**遍历（`w:p`→paragraph/heading、`w:tbl`→表格）；Heading 样式 → `block_type="heading"`；表格渲染为 GitHub markdown（首行表头 + `---` 分隔）。
- `app/parsers/txt_parser.py` — `TxtParser`：chardet 采样头 64KiB 探测编码，失败回退 `utf-8/replace`；CRLF/CR 归一 LF；整文一个 block。
- `app/parsers/__init__.py` — 包入口统一 import 三个解析器模块（`@register` 自注册在此触发），`import app.parsers` 即完成全部注册。
- `app/services/parsing_service.py` — `parse_and_store(session, doc_version_id)`：MinIO 取原始文件 → 注册表分派 → 成功：JSON（ensure_ascii=False）写 `parsed-text/{doc_version_id}.json` + `parse_status='parsed'`；失败：`parse_status='failed'` + `job_steps`（`step_name='parse'`，`error_message`=traceback 摘要 ≤2000 字符）后原异常上抛（F 决定任务级重试），失败回写自身异常不再外泄。
- `tests/test_d2_parsers.py` — 9 个离线用例（三格式全部内存构造：PyMuPDF/python-docx 自产字节；注册表三类型；对象键约定）。

## 实现说明

- **契约演进（D1→D2）**：`BaseParser` 改为 `parse(file_path)` 模板方法 + `parse_bytes(data)` 抽象核心——解析器不落盘（测试零 fixture 文件），管道层少一次临时文件往返；D1 测试同步更新。
- **注册表发现机制**：`import app.parsers` 即注册全部解析器（`from app.parsers.registry import ...` 亦触发父包 `__init__`）；live E2E 首跑暴露「探针未 import 解析器模块导致注册表为空」，已通过包入口 import 修复——这是自注册模式的关键一环。
- **live E2E**（真库+真 MinIO）：真实 3 页 PDF → `parse_and_store` → 3 blocks（页码 [1,2,3]）、metadata 保留、`parsed-text/{vid}.json` 回读含 `doc_version_id/file_type/text/blocks`；损坏字节 → `FileDataError` → `parse_status='failed'` + `job_steps.error_message`（1178 字符 traceback 摘要）；清理零残留。
- 质量门禁：ruff/black/mypy（51 文件）零错误，pytest **129 passed**。

## 关联任务

- 依赖 [D1](d1-parser-abstraction.md)、[B3](b3-storage-layer.md)；被 [D3 清洗](d3-cleaning.md) 使用。
