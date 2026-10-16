# 运维与恢复手册

## 健康检查

- 存活：`GET /health/live`
- 管理诊断：owner/admin 登录后访问 `GET /api/v1/admin/health`
- Ollama：后端检查 `/api/tags`
- ComfyUI：后端检查 `/system_stats`

管理诊断只返回组件状态、队列长度和当前租约任务 ID，不返回 URL、Access Header、凭据或远程响应正文。

## 生成任务恢复

1. PostgreSQL 是任务、步骤和素材的权威状态。
2. 已保存 `remote_prompt_id` 的任务必须先查询 ComfyUI history/queue，再决定继续追踪或人工处理。
3. Cloudflare `1033`、WebSocket 中断或 Worker 重启都不能授权再次调用 `/prompt`。
4. 提交结果不确定且没有持久化 `prompt_id` 时，将任务置为 `needs_attention`，禁止自动重复生成。
5. Redis GPU 租约使用 owner token、TTL、续租和 compare-and-delete；租约丢失后下一远程步骤必须停止。

## 常见稳定错误码

- `REMOTE_AUTH_FAILED`：检查 Service Token 是否存在和权限是否正确，不记录其值。
- `REMOTE_TIMEOUT` / `REMOTE_SOFT_TIMEOUT`：先查远程 history/queue，避免重复提交。
- `REMOTE_OUT_OF_MEMORY`：确认 Ollama 已按 `keep_alive: "0s"` 卸载，再检查 GPU 占用。
- `WORKFLOW_VALIDATION_FAILED`：核对工作流版本和允许参数。
- `DOWNLOAD_INTERRUPTED`：可从已有 history 输出重新下载，不重新生成。
- `STORAGE_WRITE_FAILED`：检查 MinIO 健康、桶和配额。
- `GPU_LEASE_LOST`：停止下一远程步骤，检查 Redis 与 Worker 心跳。

## 备份

- PostgreSQL：每日逻辑备份，并周期性验证恢复。
- MinIO：版本化或对象复制；数据库与对象快照使用同一恢复点标签。
- Redis：不是生成事实的唯一来源，但保留 AOF 可减少恢复扫描。

恢复演练必须验证：任务与步骤状态、素材 object key、父子素材 lineage、预签名访问以及视频可解码。
