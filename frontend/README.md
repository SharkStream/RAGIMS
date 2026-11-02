# RAGIMS Frontend (H1)

React 18 + Vite 5 + TypeScript + Ant Design Pro（ProLayout 布局）。

## 启动（首次需本机安装依赖）

```powershell
cd frontend
pnpm install        # 或 npm install
pnpm dev            # http://localhost:5173
pnpm build          # 类型检查 + 产物构建
```

## 结构

- `src/api/client.ts` — axios 封装：统一响应 `{code,message,data}` 拦截器、成功解包、非 OK/网络错误归一为 `ApiError`
- `src/api/index.ts` — 类型化调用（documents / jobs / search / stats）
- `src/App.tsx` — ProLayout 侧边栏：文档 / 任务 / 检索测试 / 设置
- `src/pages/*` — 四个页面（H2–H5 实现）
- `.env.development` — `VITE_API_BASE_URL`（默认 http://127.0.0.1:8000/api）

## 后端联调

后端 FastAPI 默认 `http://127.0.0.1:8000`，CORS 已放行 5173（`APP__CORS_ORIGINS`）。
