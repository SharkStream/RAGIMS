# D5 · 单元测试

> **阶段**：D 解析、清洗、切分（4-5 天）　**依赖**：D2、D3、D4　**工时**：约 1 天

## 目标

为解析、清洗、切分建立样例夹具与端到端单测，覆盖边界用例。

## 实施步骤

### 1. 样例文件 `backend/tests/fixtures/`
- 准备 PDF、DOCX、TXT 各至少一个样例文件。

### 2. 端到端单测 `backend/tests/test_parsing_pipeline.py`
- 覆盖「解析 → 清洗 → 切分」全链路。

### 3. 边界用例
- 空文件、加密 PDF、超大文件、超长单段。

## 验收标准

- [x] 三种格式样例均能产出非空 chunk 列表。
- [x] 边界用例不崩溃、有明确处理（跳过/报错）。
- [x] 覆盖率计入阶段 I 的核心模块覆盖率目标（≥70%）。（覆盖率工具 pytest-cov 留待 I1 安装汇总；本任务已覆盖 `app/parsers/*`、`services/cleaning.py`、`app/chunkers/*` 全部公开路径）

## 产出物（D5 完成，D 阶段全部收官）

- `tests/fixtures/build_samples.py` — 确定性样例构造器（`build_pdf_bytes` 含页眉 3 页 / `build_encrypted_pdf_bytes` AES-256 / `build_docx_bytes` heading+段落+表格 / `build_txt_bytes`）+ `main()` 生成落盘样例（沙箱拒写时逐文件 skip 提示，退出码 0）。
- `tests/fixtures/README.md` — 说明「为何内存构造、如何生成落盘样例、样例覆盖点」。
- `tests/conftest.py` — 将 `tests/fixtures/` 加入 `sys.path`（`import build_samples` 直用）。
- `tests/test_parsing_pipeline.py` — 11 个用例：
  - **端到端**（验收 1）：三格式 parse→clean→chunk 全链非空 chunks；pdf 页码/页眉剥离/metadata、docx heading+paragraph+table 全保留、txt 无页码；hash 唯一且构造器确定性（重复运行同 hash）。
  - **边界**（验收 2）：空 txt → 全链 0 chunks 不崩；空 pdf → `EmptyFileError`；空 docx → `BadZipFile`；**加密 PDF → `ValueError("PDF is password-protected...")` 明确信息**（`PdfParser` 新增 `needs_pass` 检测）；超大文本（~2048 tokens 单块）→ 正确切分不拒；超长单段（~5000 tokens）→ 窗口不变量（满窗 512、尾窗 >50）；空白 PDF → 0 chunks 不崩。

## 实现说明

- **样例不落盘的原因**：沙箱禁止子进程写盘（含二进制），测试统一走内存构造——与 D2 的 `parse_bytes` 契约天然配套；`build_samples.py main()` 保留落盘能力供非受限环境使用。
- **加密 PDF 明确报错**：pymupdf 默认在 `get_text` 时抛裸 `ValueError`（无信息），在 `PdfParser.parse_bytes` 开头检测 `needs_pass` 并抛带上下文的消息——F 流水线把异常写入 `job_steps.error_message` 时用户可读。
- 质量门禁：ruff/black/mypy（54 文件）零错误，pytest **173 passed**（D 阶段累计 +51）。

## 关联任务

- 依赖 [D2](d2-format-parsers.md)、[D3](d3-cleaning.md)、[D4](d4-chunking.md)；被 [I1 自动化测试](i1-automated-tests.md) 汇总。
