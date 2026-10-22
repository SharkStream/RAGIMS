# D1 · 解析器抽象

> **阶段**：D 解析、清洗、切分（4-5 天）　**依赖**：B　**工时**：约 0.5 天

## 目标

定义解析器统一接口与注册表，按 `file_type` 分派具体解析器。

## 实施步骤

### 1. 解析结果模型 `backend/app/parsers/base.py`
- `ParsedDocument`（dataclass）：`text: str`、`blocks: list[Block]`、`metadata: dict`。
- `Block`（dataclass）：`text: str`、`page: int | None`、`block_type: str`（如 `paragraph`、`table`、`heading`）。

### 2. 抽象接口
- `BaseParser`（ABC）：`parse(file_path: str) -> ParsedDocument`。
- 常量 `SUPPORTED_TYPES = {"pdf", "docx", "txt"}`。

### 3. 注册表 `backend/app/parsers/registry.py`
- `get_parser(file_type: str) -> BaseParser`，未知类型抛 `UnsupportedFileType`。
- 用装饰器或字典注册 `pdf`/`docx`/`txt` 映射到具体类（D2 实现）。

## 验收标准

- [x] 三种 `file_type` 能通过注册表拿到对应解析器。
- [x] 未知类型抛出明确异常。

## 产出物（D1 完成）

- `app/parsers/base.py` — `Block`（`text/page/block_type`，dataclass slots）、`ParsedDocument`（`text/blocks/metadata`，解析-清洗-切分间的统一货币）、`BaseParser` ABC（`parse(file_path) -> ParsedDocument`，约定**无副作用**——只读文件返回内存结果，落 MinIO/状态回写是流水线职责）、`SUPPORTED_TYPES = {pdf, docx, txt}`（与 B1 `documents.file_type` 域对齐）、`UnsupportedFileType`（含 supported 列表的明确异常）。
- `app/parsers/registry.py` — `@register(file_type)` 类装饰器（重复注册/超出 SUPPORTED_TYPES → `ValueError`）、`get_parser(file_type)`（未知类型 → `UnsupportedFileType`，每次返回新实例）、`registered_types()`。
- `tests/test_d1_parsers.py` — 11 个离线用例（dataclass 默认值、ABC 不可实例化、三类型分派、新实例不变量、未知类型异常、注册守卫；registry 快照 fixture 保证全局态不泄漏）。

## 实现说明

- **D1/D2 边界**：D1 只交付抽象与注册机制，验收用「注册 fake → 分派」验证；三个真实解析器（D2）在各自模块 `@register` 后，`get_parser` 对真实三类型自动生效。
- **数据流契约**：`ParsedDocument.blocks[].page` 保留页码粒度（D3 清洗、D4 切分的 chunk `page` 来源）；`metadata` 承载文件级事实（标题/作者，PDF 解析器产出）。
- 质量门禁：ruff/black/mypy（47 文件）零错误，pytest **120 passed**。

## 关联任务

- 依赖 [B 数据模型](b1-db-tables.md)；被 [D2 格式解析器](d2-format-parsers.md) 实现。
