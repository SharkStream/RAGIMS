# Test fixtures（D5）

本目录存放解析管线的样例材料。

## 为什么没有样例二进制文件

沙箱环境禁止子进程写盘（PyMuPDF/python-docx 的二进制产物无法由测试落盘），
因此**测试全部使用内存构造的字节**（`build_samples.py` 中的 `*_bytes` 构造器），
与 D2 的 `BaseParser.parse_bytes` 契约配套——样例输入确定性可复现，等价于
落盘 fixture，且避免二进制漂移。

## 生成真实样例文件（可选，供人工检查/外部工具）

在非受限环境于 `backend/` 下运行：

```powershell
env\Scripts\python.exe tests\fixtures\build_samples.py
```

会生成 `sample.pdf / sample.docx / sample.txt`（含页眉样例，可用于人工
验证 D3 页眉页脚剥离）。

## 样例构成

| 文件 | 内容 | 覆盖点 |
| --- | --- | --- |
| `sample.pdf` | 3 页，每页 1 行页眉（`Q3 2026 Confidential`）+ 标题行 + 6 行正文 | 多页/页码、页眉剥离、metadata |
| `sample.docx` | Heading + 两个段落 + 2×2 表格 | heading/table block_type、文档顺序 |
| `sample.txt` | 10 行 utf-8 文本 | 单 block、编码探测 |
| 加密 PDF（仅内存） | AES-256 用户密码保护 | D5 边界：明确报错不崩溃 |
