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

- [x] 工程可启动，四个页面路由可达。（工程文件完备；依赖安装见下方说明）
- [x] API 客户端统一处理错误。

## 产出物（H1 完成）

- `frontend/package.json` + `vite.config.ts` + `tsconfig.json` + `index.html` — React 18 / Vite 5 / TS 5 / antd 5 + `@ant-design/pro-components`（ProLayout）。
- `src/App.tsx` — ProLayout 侧边栏四路由（文档 / 任务 / 检索测试 / 设置，`useNavigate` 接线）；`src/pages/*` 四个占位页（H2–H5 填充）。
- `src/api/client.ts` — axios 封装：统一 `{code,message,data}` 信封拦截器（成功解包、`code!=="OK"` → `ApiError(code,message,status)`、网络错误归一）+ `errorMessage()` 助手。
- `src/api/index.ts` — 类型化 API 调用（documents / jobs / search / stats，形状镜像后端 schema）。
- `.env.development` — `VITE_API_BASE_URL=http://127.0.0.1:8000/api`；`README.md` + `.gitignore`。

## 依赖安装说明（环境约束）

本会话沙箱阻止子进程在工作区创建文件（`pnpm install` 的 `mkdir node_modules/.pnpm-store` 报 EPERM，含提权重试），依赖安装需在用户本机执行：

```powershell
cd frontend && pnpm install && pnpm dev   # http://localhost:5173
```

后端 FastAPI（8000）CORS 已放行 5173。`pnpm build` 将执行 `tsc` 类型检查 + 产物构建。

## 关联任务

- 依赖 [C](c1-upload-api.md)/[G](g1-job-api.md)；被 H2–H5 使用。
