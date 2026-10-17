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

- [ ] 三种 `file_type` 能通过注册表拿到对应解析器。
- [ ] 未知类型抛出明确异常。

## 关联任务

- 依赖 [B 数据模型](b1-db-tables.md)；被 [D2 格式解析器](d2-format-parsers.md) 实现。
