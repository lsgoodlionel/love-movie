# 运维与恢复手册

## 健康检查

- 存活：`GET /health/live`
- 管理诊断：owner/admin 登录后访问 `GET /api/v1/admin/health`
- Ollama：后端检查 `/api/tags`
- ComfyUI：后端检查 `/system_stats`

管理诊断只返回组件状态、队列长度和当前租约任务 ID，不返回 URL、Access Header、凭据或远程响应正文。

模型路由按租户隔离；数据库中 `tenant_id` 为空的记录是平台只读默认值，租户管理员只能新增或修改本租户覆盖项。Worker 在启动时载入启用路由，修改后需滚动重启 Worker 才会生效。

## 生成任务恢复

1. PostgreSQL 是任务、步骤和素材的权威状态。
2. Worker 启动会扫描未完成任务；已保存 `remote_prompt_id` 的任务先查询 ComfyUI history，再查询 queue，并用同一任务和 prompt 恢复追踪。
3. Cloudflare `1033`、WebSocket 中断或 Worker 重启都不能授权再次调用 `/prompt`。已有 `prompt_id` 的 `REMOTE_SOFT_TIMEOUT`、Tunnel/网络错误、下载中断或对象存储暂时失败进入可恢复的“需人工处理”范围；Worker 重启后仍先查 history/queue 并复用同一远程任务。
4. 提交结果不确定且没有持久化 `prompt_id` 时，将任务置为 `needs_attention`，禁止自动重复生成。
5. Redis GPU 租约使用 owner token、TTL、续租和 compare-and-delete；租约丢失后下一远程步骤必须停止。
6. 取消已提交任务时，平台先记录取消意图，再尝试从 ComfyUI queue 删除并中断当前单 GPU 作业；远程取消未确认会写入事件，但本地不会继续下载或归档结果。

## 常见稳定错误码

- `REMOTE_AUTH_FAILED`：检查 Service Token 是否存在和权限是否正确，不记录其值。
- `REMOTE_TIMEOUT` / `REMOTE_SOFT_TIMEOUT`：已有 `prompt_id` 时保留为可恢复任务，先查远程 history/queue，避免重复提交；没有远程 ID 时根据发生阶段转人工处理或失败。
- `REMOTE_SUBMISSION_UNKNOWN`：`POST /prompt` 结果不确定，任务进入人工处理，不得自动再次提交。
- `REMOTE_CANCEL_UNCONFIRMED`：保持人工处理状态，先确认 queue/history，避免把仍在运行的任务误报为已取消。
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
