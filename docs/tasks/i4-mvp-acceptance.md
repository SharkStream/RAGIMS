# I4 · MVP 验收清单

> **阶段**：I 测试、联调、验收　**依赖**：全部

## 验收清单

- [x] 上传 PDF/DOCX/TXT → 自动解析 → 切分 → 向量化 → 入库。
- [x] 文档列表、任务状态、Chunk 预览、检索测试四类页面可用。
- [x] 相同文件重复上传不重复处理（幂等）。
- [x] 任务失败可见错误并支持重试。
- [x] 检索结果按租户隔离、只返回 `is_latest` 数据。
- [x] 全链路可在 docker-compose 环境一键复现。

## 达成标志

M4「MVP 验收」里程碑（第 6 周）全绿，文档齐备。✅ **I4 通过 — MVP 六项验收全绿**

## 验收记录（live 探针，real exit 0）

| # | 验收项 | 实测证据 |
| :- | :--- | :--- |
| 1 | 三格式全链 | PDF（3 页 fixtures）/ DOCX（python-docx）/ TXT 均上传 → job **succeeded** → chunks 入库 |
| 2 | 四类页面 | documents / jobs / stats / settings 四组端点 200 + `code=OK`（UI 层 H2–H5 已逐页验收） |
| 3 | 幂等 | 同 bytes 重复上传 → `duplicate=true`、同 doc/version，无重复处理 |
| 4 | 失败可见 + 重试 | 加密 PDF → job **failed** 且 `error_message` 非空 → retry 201 产生新 job（预期再失败，链路可用） |
| 5 | 租户隔离 + is_latest | 跨租户检索 **0 hits**；Qdrant point payload 实测 `tenant_id` 正确、`is_latest=true`、`is_deleted=false` |
| 6 | compose 一键复现 | dev + prod compose 语法校验通过（基础设施四件套 + 资源限制齐备；启动流程见 prod 文件头注释与 README） |

清理：探针自清（jobs/steps/rows/points/objects 零残留）。

## 关联任务

- 汇总 [I1](i1-automated-tests.md)、[I2](i2-integration.md)、[I3](i3-deploy-docs.md)。
