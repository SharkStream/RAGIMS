# API 参考（I3 · 由 OpenAPI 生成）

来源：`GET /openapi.json`（FastAPI 0.1.0，生成于探针运行时）。
交互式文档：`/docs`（Swagger UI）· `/redoc`。所有路径前缀 `/api`（health 除外）。
统一响应信封 `{code, message, data}`；`code === "OK"` 表示成功，其余为 `ERR_*` 错误码。

## 健康检查

| 方法 | 路径 | 说明 |
| :-- | :-- | :-- |
| GET | `/healthz` | Liveness probe (no external dependencies) |
| GET | `/readyz` | Readiness probe (MySQL / Redis / Qdrant; 503 when any is down) |

## 文档（C1/C2）

| 方法 | 路径 | 说明 |
| :-- | :-- | :-- |
| POST | `/api/documents/upload` | Upload a document (pdf/docx/txt/md, idempotent on content hash); same name + new hash appends vN+1 (J1) |
| GET | `/api/documents` | List documents (filter / search / paginate; excludes deleted) |
| GET | `/api/documents/{doc_id}` | Document detail with its latest version |
| PATCH | `/api/documents/{doc_id}` | Metadata-only update: title / tags / access_level / datasource_id — zero jobs, zero re-embed (J3) |
| DELETE | `/api/documents/{doc_id}` | Soft delete (status=deleted; async object cleanup is out of MVP) |
| GET | `/api/documents/{doc_id}/chunks` | Chunks of the current version, ordered by chunk_index |
| POST | `/api/documents/{doc_id}/reprocess` | Create a reprocess job for the latest version and dispatch it |
| POST | `/api/documents/{doc_id}/jobs/{job_id}/cancel` | Cooperatively cancel a pending/running job |
| GET | `/api/documents/{doc_id}/versions` | Version history, newest first, paged (J2) |
| GET | `/api/documents/{doc_id}/versions/{version}` | Version detail by ordinal (J2) |
| GET | `/api/documents/{doc_id}/versions/{version}/chunks` | Chunks of a specific version, paged (J2) |
| POST | `/api/documents/{doc_id}/versions/{version}/activate` | Set a parsed historical version as latest (= rollback): MySQL flip + Qdrant payload flip, idempotent, 503 on Qdrant failure (J4) |
| DELETE | `/api/documents/{doc_id}/versions/{version}` | Physically reclaim a non-latest version: chunk rows + Qdrant points + MinIO raw/parsed objects + job trail; latest → 409 (J4) |

## 任务（G1）

| 方法 | 路径 | 说明 |
| :-- | :-- | :-- |
| GET | `/api/jobs` | Paged job list (filters: status / job_type / doc_id) |
| GET | `/api/jobs/{job_id}` | Job detail |
| GET | `/api/jobs/{job_id}/steps` | Steps of a job, ordered by step_order (timing/status/errors) |
| POST | `/api/jobs/{job_id}/retry` | Re-dispatch a failed job as a NEW job row |
| POST | `/api/jobs/{job_id}/cancel` | Cooperatively cancel a pending/running job |

## 检索测试（G2）

| 方法 | 路径 | 说明 |
| :-- | :-- | :-- |
| POST | `/api/search/test` | Retrieval test: embed query + Qdrant search（tenant 硬过滤 + K4 角色密级白名单 `access_level ∈ MatchAny(白名单)`，viewer 不可见 confidential） |

## 认证（K2）

| 方法 | 路径 | 说明 |
| :-- | :-- | :-- |
| POST | `/api/auth/login` | `{username, password}` → `{token, token_type, expires_in, user}`；错密码/未知/禁用统一 401（防枚举）；登录进审计 `auth.login` |
| GET | `/api/auth/me` | 回显当前身份（验签 + 查 users 行；role/tenant/status 以 DB 为准） |

携带方式：`Authorization: Bearer <token>`（12h 过期）。后端 `SECURITY__AUTH_REQUIRED=true` 时无 token 一律 401；false（dev 默认）时匿名回退 stub admin，带 token 仍严格校验。

## 用户管理（K7 · admin-only）

| 方法 | 路径 | 说明 |
| :-- | :-- | :-- |
| POST | `/api/auth/users` | 本租户建号 `{username, password, role, email?}` → 201；重名 409；密码 ≥8 位且含字母数字否则 422；审计 `auth.user_created` |
| GET | `/api/auth/users` | 本租户用户分页（page/page_size≤100、status 过滤）；**不回传 password_hash** |
| PATCH | `/api/auth/users/{id}` | `{role?/status?/password?}` 任意组合：角色变更审计 `auth.role_changed`（detail from→to）、禁用/启用 `auth.user_disabled`/`auth.user_enabled`、重置密码 `auth.password_reset`（不落明文）；**role/status 立即生效**（现有 token 每次请求查库）；跨租户目标 404；修改自己 409（防自锁） |

## 审计日志（K1）

| 方法 | 路径 | 说明 |
| :-- | :-- | :-- |
| GET | `/api/audit-logs` | 分页（page/page_size≤100）+ `action` / `resource_type` / `resource_id` 过滤；租户只取自身份；倒序。动作：`doc.upload / doc.meta_patch / doc.activate / doc.version_delete / doc.soft_delete / doc.reprocess / auth.login` |

## 统计（G3）

| 方法 | 路径 | 说明 |
| :-- | :-- | :-- |
| GET | `/api/stats` | Dashboard aggregates (documents / chunks / job success / today) |

## 数据源

| 方法 | 路径 | 说明 |
| :-- | :-- | :-- |
| GET | `/api/datasources` | List the tenant's datasources |
| POST | `/api/datasources` | Create a local datasource (other types → 501) |

## 设置（H5）

| 方法 | 路径 | 说明 |
| :-- | :-- | :-- |
| GET | `/api/settings/effective` | Effective settings: default embedding model + chunking (read-only) |

## 错误码速查

| HTTP | code | 场景 |
| :-- | :-- | :-- |
| 400 | ERR_BAD_REQUEST | 通用请求错误 |
| 401 | ERR_UNAUTHORIZED | 未认证 |
| 403 | ERR_FORBIDDEN | 无权限 |
| 404 | ERR_NOT_FOUND | 文档/任务不存在或跨租户 |
| 409 | ERR_CONFLICT | 状态不允许（如 succeeded 重试、cancel 冲突） |
| 413 | ERR_FILE_TOO_LARGE | 超过 50MB 上限 |
| 415 | ERR_FILE_TYPE_NOT_ALLOWED | 非 pdf/docx/txt/md |
| 422 | ERR_VALIDATION | 请求体校验失败 |
| 500 | ERR_INTERNAL | 服务内部错误 |
| 501 | ERR_NOT_IMPLEMENTED | 非 local 数据源 |
| 503 | ERR_UNAVAILABLE | 依赖（MinIO/Redis）不可用 |

## 请求/响应示例

```bash
# 上传（multipart）
curl -F "file=@doc.pdf" http://127.0.0.1:8000/api/documents/upload
# => {"code":"OK","message":"uploaded","data":{"doc_id":"…","job_id":"…","duplicate":false,…}}

# 检索测试（tenant 由认证 stub 固定，请求体不含租户字段）
curl -X POST http://127.0.0.1:8000/api/search/test \
  -H "Content-Type: application/json" \
  -d '{"query":"季度复盘","top_k":5,"filters":{"doc_id":"…"}}'
# => data.hits[{score,text,doc_id,version,page,metadata}] + took_embedding_ms/search/total

# 任务步骤（含每步耗时）
curl http://127.0.0.1:8000/api/jobs/{job_id}/steps
# => data.items[{step_order,step_name,status,duration_ms,output,error_message}]
```
