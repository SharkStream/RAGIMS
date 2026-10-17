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

- [ ] 三种格式样例均能产出非空 chunk 列表。
- [ ] 边界用例不崩溃、有明确处理（跳过/报错）。
- [ ] 覆盖率计入阶段 I 的核心模块覆盖率目标（≥70%）。

## 关联任务

- 依赖 [D2](d2-format-parsers.md)、[D3](d3-cleaning.md)、[D4](d4-chunking.md)；被 [I1 自动化测试](i1-automated-tests.md) 汇总。
