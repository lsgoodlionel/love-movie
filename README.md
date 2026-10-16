# love-movie
# 爱视频（Love Movie）

面向个人与内部团队的 AI 图片、视频和长篇动画生产平台。首个里程碑是在中文 Web 页面输入文字，真实调用远程 Ollama 与 ComfyUI，生成可追踪、可预览、可下载的图片和单镜头视频。

## 当前状态

项目处于首个真实生成切片的实施阶段。系统设计和任务计划位于：

- `docs/superpowers/specs/2026-10-16-ai-video-studio-design.md`
- `docs/superpowers/plans/2026-10-16-first-generation-slice.md`

## 技术架构

- Web：Next.js + TypeScript
- API/Worker：FastAPI + Python 3.12
- 数据：PostgreSQL、Redis、MinIO
- 媒体处理：FFmpeg
- 推理：受 Cloudflare Access 保护的远程 Ollama 与 ComfyUI

## 安全要求

浏览器不会直接访问远程 GPU 服务。Cloudflare Access 凭据只能通过服务端 Secret 或环境变量注入，禁止提交 `.env`、凭据、原始私密提示词或生成媒体。

## 本地启动

实现中的开发入口：

```bash
cp .env.example .env
docker compose up -d --build
```

`.env.example` 只列出配置名称与安全示例；真实 Secret 必须由部署环境提供。
