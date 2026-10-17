# H1 · 前端工程初始化

> **阶段**：H 前端管理界面（5-6 天）　**依赖**：C/G　**工时**：约 1 天

## 目标

初始化前端工程、路由布局与 API 客户端。

## 实施步骤

### 1. 工程初始化
- `frontend/`：React + Vite + TypeScript + Ant Design Pro。
- 路由与布局：侧边栏 `文档 / 任务 / 检索测试 / 设置`。

### 2. API 客户端 `frontend/src/api/client.ts`
- axios 封装：拦截器 + 统一错误提示（对接后端统一响应 `code/message/data`）。

### 3. 环境变量
- `VITE_API_BASE_URL` 配置后端地址。

## 验收标准

- [ ] 工程可启动，四个页面路由可达。
- [ ] API 客户端统一处理错误。

## 关联任务

- 依赖 [C](c1-upload-api.md)/[G](g1-job-api.md)；被 H2–H5 使用。
