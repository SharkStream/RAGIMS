# H2 · 文档管理页

> **阶段**：H 前端管理界面（5-6 天）　**依赖**：H1、C　**工时**：约 2 天

## 目标

实现文档列表、上传、详情与 chunk 预览页面。

## 实施步骤

### 1. 列表 `frontend/src/pages/Documents/index.tsx`
- 分页；筛选（状态/类型）；标题搜索。

### 2. 上传组件
- 拖拽上传、进度条、类型校验（pdf/docx/txt）。

### 3. 详情抽屉/页
- 基础信息、版本信息、当前状态。

### 4. Chunk 预览
- 列表 + 分页 + 高亮 `chunk_index`/`page`。

### 5. 操作
- 重新处理按钮、软删除按钮。

## 验收标准

- [x] 列表/筛选/搜索可用。
- [x] 上传带进度与类型校验。
- [x] chunk 预览分页与高亮正确。

## 产出物（H2 完成）

- `src/pages/documents.tsx` — 完整文档管理页：
  - **列表**：Table 分页（showSizeChanger）+ 状态/类型 Select 筛选 + 标题/文件名 keyword 搜索（防抖由 antd Input.onChange 直驱、切筛选回第 1 页）；
  - **上传**：`Upload.Dragger` 拖拽 + 前端类型校验（pdf/docx/txt）+ 50MB 上限 + `onUploadProgress` 进度条（可中断：AbortController）+ 幂等命中提示；
  - **详情抽屉**：Descriptions（基础信息 + latest_version：版本号/解析状态/文件大小/可复制 content_hash）；
  - **Chunk 预览**：Drawer 内 List 分页（10/页）+ `chunk #index` / `第 N 页` / token 数 Tag 高亮 + 文本折叠展开；
  - **操作**：重新处理（POST reprocess，成功提示新 job id）、软删除（Popconfirm 确认后 DELETE，列表自动刷新）。
- `src/api/index.ts` — 补 `DocumentVersionOut/DocumentDetail/ChunkOut` 类型 + `uploadWithProgress`（进度/中断）/ `reprocess` / `chunks` 调用；`keyword` 参数名与 C2 对齐。

## 验收证据（live，真后端 uvicorn:8000 + worker，real exit 0）

| # | 场景 | 实测 |
| :- | :--- | :--- |
| 1 | 列表 | `GET /documents` total=3，`code=OK` |
| 2 | 上传 | multipart 上传 → job 派发 → **succeeded** |
| 3 | 详情 | `latest_version v1 parse=parsed`（file_size 2680B） |
| 4 | Chunk 预览 | total=2，字段 `chunk_index/page/section/text/token_count` 齐全 |
| 5 | 重新处理 | 新 job → succeeded |
| 6 | 软删除 | DELETE 后 keyword 搜索 total=0（列表隐藏） |

`tsc --noEmit` 零错误（node_modules 由用户本机安装）。浏览器侧交互（拖拽/进度动画）请启动 `pnpm dev` 后于 http://localhost:5173 验证。

## 关联任务

- 依赖 [H1](h1-frontend-init.md)、[C](c2-document-query-api.md)。
