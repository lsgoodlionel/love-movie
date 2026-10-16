# 爱视频（Love Movie）

面向个人与内部团队的私有 AI 影像制作平台，并为后续开放注册、套餐与按生成量计费的多租户 SaaS 预留架构。当前首个可运行切片支持在中文 Web 页面输入文字，生成图片或 512×512 单镜头视频，并管理任务、进度和素材。

## 已交付能力

- 中文登录、项目、快速生成台与素材库
- 文字生成图片：768×1024、受控参数、幂等提交
- 文字生成视频：Ollama 规划提示词 → 图片首帧 → Wan 图生视频
- 当前视频安全档位：512×512、81 帧、16 FPS、20 步
- PostgreSQL 任务与事件、Redis ARQ 队列、单 GPU 可续租租约
- Worker 启动恢复：复用已保存的计划、步骤 prompt 与素材，不重复提交远程 GPU 作业
- MinIO 平台素材归档、SHA-256、300 秒预签名预览
- Web SSE 进度、刷新后历史任务恢复、图片预览和 HTML5 视频播放
- owner/admin/creator/reviewer 四种角色、租户隔离与项目成员隔离
- 租户隔离的可配置模型路由、原子 GPU/存储配额预留、用量流水和管理诊断

远程 Ollama 和 ComfyUI 只由 API/Worker 访问。浏览器构建不包含远程 AI 主机名或 Cloudflare Access Header。

## 架构

```text
浏览器 ──same-origin /api──> Next.js ──> FastAPI
                                      ├─ PostgreSQL（权威任务状态）
                                      ├─ Redis / ARQ（队列与 GPU 租约）
                                      ├─ MinIO（平台素材）
                                      └─ Worker ──> Ollama / ComfyUI
```

- Web：Next.js 16 + React 19 + TypeScript
- API / Worker：FastAPI + SQLAlchemy + Alembic + ARQ
- 基础设施：PostgreSQL 16、Redis 7、MinIO、Docker Compose
- 测试：Pytest、Vitest、Playwright

## 本地启动

1. 创建本地配置，只填写真实环境需要的值，不要提交 `.env`：

   ```bash
   cp .env.example .env
   ```

2. 启动并等待核心服务健康：

   ```bash
   docker compose up -d --build
   docker compose ps
   ```

3. 首次创建内部所有者：

   ```bash
   docker compose exec \
     -e BOOTSTRAP_OWNER_EMAIL='owner@example.com' \
     -e BOOTSTRAP_OWNER_PASSWORD='请使用强密码' \
     api python -m app.cli.bootstrap_owner
   ```

4. 打开 `http://localhost:3000/login`，登录后创建“第一个项目”，即可提交图片或视频任务。

## 开发验证

```bash
cd services/backend
uv sync
uv run alembic upgrade head
uv run pytest -q

cd ../../apps/web
npm install
npm test -- --run
npm run typecheck
npm run build

cd ../../e2e
npm install
npx playwright test
```

部署与 Secret 注入见 [docs/deployment.md](docs/deployment.md)，日常排障与恢复见 [docs/operations.md](docs/operations.md)，首个切片验收记录见 [docs/acceptance/first-generation-slice.md](docs/acceptance/first-generation-slice.md)。

后续阶段将接续实现短故事配音字幕视频，以及小说/长文本拆解为分集、场景、镜头并批量生成可继续剪辑的素材。

远程 Access 配置已通过宿主机和 API 容器双路径验证：Ollama、ComfyUI 均曾返回 200，模型清单和 CUDA 设备可读取。首次真实图片任务已取得并持久化 ComfyUI `prompt_id`，但等待期间 Tunnel 再次转为 Cloudflare `1033`（HTTP 530）；平台保留同一远程任务并进入可恢复追踪，不会盲目重复提交。图片产物、视频产物和网页播放仍需在 Tunnel 稳定后完成最终验收。
