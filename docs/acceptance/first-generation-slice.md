# 首个图片/视频生成切片验收

验收日期：2026-10-16  
分支：`codex/first-generation-slice`

## 已验证范围

- 后端领域、租户与项目成员权限、工作流、适配器、队列、启动恢复、图片/视频断点编排、任务历史和管理 API
- Web 中文快速生成台、任务状态、图片/视频预览、素材库
- 确定性浏览器流程：图片提交/预览/下载、视频模式、页面刷新
- 前端构建产物不含远程 AI 主机名或 Cloudflare Access Header 名称

## 本地证据

| 检查 | 结果 |
|---|---|
| `pytest -q` | 88 passed |
| `npm test -- --run` | 5 passed |
| `npm run typecheck` | passed |
| `npm run build` | passed，`/login`、`/generate`、`/assets` 已生成 |
| `npx playwright test` | 3 passed |
| `docker compose up -d --build` | PostgreSQL、Redis、MinIO、API healthy；Web、Worker running |
| PostgreSQL migration | `0008_tenant_reliability`；现有库与临时空库均完成 `upgrade head`，`alembic check` 无漂移 |
| Redis Worker heartbeat | present |
| 本地 API 用户流 | 登录 200、创建项目成功、项目列表 200 |
| API → Redis → Worker | 任务已被 Worker 接管；无远程凭据时稳定终态失败 |

浏览器用例使用受控 API mock 验证 UI 行为；Docker 验证覆盖真实 PostgreSQL、Redis、MinIO、API 与 Worker 启动和迁移。真实 Ollama/ComfyUI 端到端生成尚受下述 Tunnel 故障阻塞，未将 mock 结果表述为远程生成成功。

## 工作流版本

- 图片：`z_image_turbo:v1`
- 单镜头视频：`z_image_turbo:v1 + wan_i2v:v1`
- 视频限制：512×512、81 帧、16 FPS、20 步

## 远程受控烟雾验收

已将本机安全保存的网站 Service Token 注入 Git 忽略且权限为 `0600` 的本地 `.env`，没有输出或提交凭据。宿主机与 API 容器双路径检查中，Ollama `/api/tags` 和 ComfyUI `/system_stats` 均返回 200；检测到 10 个 Ollama 模型（包含三条默认路由所需模型）和 1 个 CUDA 设备。

随后通过真实 Web API 创建图片任务 `5f206e65-381f-4f40-bb5a-f93ab2a74594`，API → Redis → Worker → ComfyUI 成功，远程 `prompt_id` 已持久化。任务等待前序队列期间 ComfyUI Tunnel 再次返回 `1033`（HTTP 530），追踪窗口耗尽暴露出任务被误标为 `failed/REMOTE_SOFT_TIMEOUT` 的恢复缺口。已用回归测试修复：持久化远程 ID 的软超时现在进入可恢复状态；GPU 租约丢失使用稳定错误码；运行中取消与远程取消未确认会保留取消意图并进入 history/queue 恢复；Worker 重启使用同一 `prompt_id`，恢复为运行态时清除过期错误。修复后后端为 88 passed，真实任务已验证恢复到 `running`，没有第二次 `/prompt`。

由于 Tunnel 仍不稳定，本次尚未取得最终图片文件，也未继续提交视频任务。待 connector 稳定后继续跟踪上述远程任务；图片成功转存并预览后，再提交一个 81 帧视频完成最终验收。

记录只保留脱敏任务 ID、工作流版本、耗时和结果，不记录私密提示词、Access Header、Secret 或原始远程日志。

## 当前遗留

- 配音、字幕、时间线导出属于下一阶段短故事生产链。
- 小说/长文本分集、场景、镜头拆解及批量素材生成属于紧随其后的第二阶段。
- 公开注册、支付、套餐和按量计费在私有团队流程稳定后开放。
- 租户配额和用量账本已进入运行路径；套餐购买、账单结算、并发配额预留和运营后台仍属于公开 SaaS 阶段。
