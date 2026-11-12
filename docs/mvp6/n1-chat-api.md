# N1 · Chat API（生成 + 流式 + 引用）

> **阶段**：N 优化与扩展（RAG 完整化）　**依赖**：阶段 3/4 基线　**工时**：1-2 天
> 补齐 RAG 的「G」——本卡是 N2/N3/N4 的地基。

## 目标

`POST /api/chat`（**SSE 流式**）：query → 复用检索（四条件强制过滤 + 调用者密级白名单）→ top-k chunks 组 prompt → OpenAI 兼容 chat.completions 流式合成 → 引用溯源返回。

## 实施步骤

1. **配置**：`OPENAI__CHAT_MODEL`（新键，独立于 embedding 模型）、`CHAT__TOP_K`（默认 5）、`CHAT__MAX_HISTORY`（默认 6 轮）。
2. **检索复用**：`search_test(query, tenant_id, top_k, role=user.role)`——viewer 天然检索不到 confidential（密级 ACL 在检索层已生效，chat 无需重复实现）。
3. **Prompt 设计**（system 模板，常量文件管理）：
   - 仅依据给定上下文回答；**上下文不足时明确说不知道**（拒答策略）
   - 每个上下文块带 `[1] [2]` 编号 → 要求回答中引用编号
4. **API**：`POST /api/chat`，body `{query, conversation_id?, history?: [{role, content}]}`（MVP **无状态**：多轮历史由前端回传，窗口截断 MAX_HISTORY；服务端会话持久化延后）。
   - 响应 `text/event-stream`：`event: token`（增量文本）→ `event: done`（`{answer, citations: [{index, chunk_id, doc_id, version, page, score}], usage: {prompt_tokens, completion_tokens}}`）
   - 读路径不落审计；**token 记账**：usage 记结构化日志 + `ragims_chat_tokens_total` gauge（metrics.py 扩展）。
5. **前端**：新「对话」页（第七页）：流式气泡 + 引用折叠面板（点击引用跳转 chunk 预览）。
6. **LLM 客户端**：`app/clients/chat_client.py`（httpx 流式，与 embedder 同风格，超时/重试策略）。

## 验收标准

- [x] SSE 流式返回（curl 可见增量 token）；done 事件含 citations 且指向真实 chunk
- [x] 拒答策略进入 system prompt（单测锁定）；**mid-stream LLM 失败转为 `error` 事件**而非 500（live 实测）
- [x] 密级：检索以**调用者角色**执行（单测锁定 viewer 白名单传导）
- [x] chat tokens 进 metrics（`ragims_chat_tokens_total{kind}`）；`tsc` 0 错误；门禁全绿（**373 passed**）
- [x] live 验证：SSE 通道 200 + event-stream ✓；**端到端回答需配置 `OPENAI__CHAT_MODEL`** 为网关实际支持的模型（默认 gpt-4o-mini 在自建网关上报 Model not exist——属环境配置，.env.example 已补提示）

## 关联任务

- N2（检索模式增强直接提升 chat 质量）、N3（生成质量评估的对象）、N4（注入防护与限流作用于此）。
