# D3 · 清洗

> **阶段**：D 解析、清洗、切分（4-5 天）　**依赖**：D2　**工时**：约 1 天

## 目标

对解析产物去噪、归一化，保留块级结构（页码、段落类型），提升后续切分与检索质量。

## 实施步骤

### 1. 清洗模块 `backend/app/services/cleaning.py`
- `clean(parsed: ParsedDocument) -> ParsedDocument`。

### 2. 规则
- **去噪**：压缩多余空白、剔除控制字符、去除页眉/页脚重复行。
- **归一化**：统一换行（`\r\n`→`\n`）。
- **去重**：去重连续重复段落。
- **可选语言检测**：简单启发式（避免乱码文本入库）。
- **保留块级结构**：清洗后 `blocks` 仍含 `page`、`block_type`。

## 验收标准

- [x] 清洗后无明显噪声（空白/控制字符/页眉页脚重复）。
- [x] 块级结构（页码、段落类型）不丢失。

## 产出物（D3 完成）

- `app/services/cleaning.py` — `clean(parsed: ParsedDocument) -> ParsedDocument`：**纯函数**（返回新对象，输入不被修改），四遍处理：
  1. **归一化**：`\r\n`/`\r` → `\n`
  2. **去噪**：剔除控制字符/零宽字符/BOM（保留 `\n`）；行内空白压缩、行首尾修剪
  3. **去重**：block 内相邻重复行去重；相邻重复 block 去重
  4. **页眉页脚**：跨 **≥3 个不同页** 在 block 首行/末行重复出现的短行（≤120 字符）按边缘剥离；计数按 line×page 去重（单行 block 的首尾是同一行，不重复计页）；<3 页不启用（信号太弱）；**中间行不参与**（避免误伤正文）
  5. **乱码丢弃**：U+FFFD 占比 >5% 的 block 剔除（decode 回退的兜底）；清洗后为空的 block 丢弃
  - `metadata["cleaning"]` 记录统计（dropped_garbled/header_footer/duplicate/empty）；`page`/`block_type` 原样保留
- `tests/test_d3_cleaning.py` — 18 个离线用例（归一化/去噪/去重/页眉页脚含反例/乱码/空块/结构保留/不可变性/统计 + 与真实 PdfParser 输出的集成用例）。

## 实现说明

- **纯内存流水线**：`clean` 只依赖 `ParsedDocument`，无 IO——D2 解析 → D3 清洗 → D4 切分可在 worker 内串联调用，不碰库和对象存储（落盘是 D2/F 的 `parse_and_store` 职责，切分结果落盘归 D4/F）。
- **页眉页脚算法细节**：初版按「出现次数」计页，单行 block（首行=末行）重复计数导致误判——E2E 前的单测已揪出，改为 line×page 集合计数。页脚若含页码（每行不同）不会被识别——MVP 接受此局限（页码行通常在 D4 切分后对检索影响有限，后续可加正则规则）。
- 质量门禁：ruff/black/mypy（52 文件）零错误，pytest **147 passed**。

## 关联任务

- 依赖 [D2](d2-format-parsers.md)；被 [D4 切分](d4-chunking.md) 使用。
