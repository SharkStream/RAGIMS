# D6 · 阶段 D 验收标准

> **阶段**：D 解析、清洗、切分　**依赖**：D1–D5

## 验收清单

- [ ] 三种格式样例均能产出非空 chunk 列表。
- [ ] chunk 的 `token_count` 与 `chunk_size` 配置一致（±overlap）。
- [ ] 解析失败可正确落库并可见错误信息。

## 达成标志

「上传文件 → 解析 → 清洗 → 切分」离线处理能力就绪，为 E 阶段向量化提供稳定输入。

## 关联任务

- 上游：[D1](d1-parser-abstraction.md)–[D5](d5-unit-tests.md)。
- 下游：[E Embedding + Qdrant 入库](e1-embedding-client.md)。
