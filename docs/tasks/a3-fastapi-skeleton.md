# A3 · FastAPI 骨架

> **阶段**：A 项目脚手架与基础设施（3-4 天）　**依赖**：A1、A2　**工时**：约 1 天

## 目标

搭建 FastAPI 应用入口、健康检查、统一响应结构与全局依赖，作为后续所有 API 的基座。

## 实施步骤

### 1. 应用入口 `backend/app/main.py`
- 创建 `FastAPI` 实例，配置 CORS（允许本地前端端口）。
- 注册路由与全局异常处理器。
- 启动时调用 `setup_logging()`。

### 2. 健康检查
- `GET /healthz`：进程存活（无外部依赖）。
- `GET /readyz`：探测 MySQL / Redis / Qdrant 连通性（任一失败返回 503）。

### 3. OpenAPI 文档
- 确认 `/docs`（Swagger UI）可访问，标题/版本来自 `Settings`。

### 4. 统一响应结构
- 文件：`backend/app/schemas/common.py`
- 定义 `ApiResponse[T]`（`code` / `message` / `data`）与分页 `PageResult[T]`（`items` / `total` / `page` / `page_size`）。
- 错误码常量：`backend/app/core/errors.py`（如 `ERR_NOT_FOUND`、`ERR_DUPLICATE`、`ERR_VALIDATION`）。

### 5. 全局依赖
- 文件：`backend/app/core/deps.py`
- `get_db()`：请求级 DB session（`yield`，`finally` 关闭）。
- `get_current_user()`：MVP 先固定返回预置默认租户/用户（阶段 3 再替换为真实认证）。

## 验收标准

- [ ] `/docs`、`/healthz`、`/readyz` 可访问。
- [ ] 统一响应结构可在任意路由复用。
- [ ] `get_db` 生命周期正确（请求结束释放连接）。

## 关联任务

- 依赖 [A1](a1-repo-structure.md)、[A2](a2-local-env.md)；被 [C1 上传接口](c1-upload-api.md)、[G1 任务接口](g1-job-api.md) 等所有 API 任务依赖。
