# 部署说明

## 环境分层

- 本地开发：Docker Compose，`.env` 仅保存在本机。
- 测试环境：独立 PostgreSQL、Redis、对象存储桶和远程计算节点。
- 生产环境：Secret Manager 或编排平台 Secret 注入，禁止使用仓库文件保存凭据。

`GENERATION_ADAPTER_MODE=fake` 仅允许 `APP_ENV=test`；其他环境启动配置校验会直接失败。

## Secret 注入

以下值只允许作为 API/Worker 进程环境变量存在：

- `APP_SECRET_KEY`
- `OBJECT_STORAGE_SECRET_KEY`
- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`
- `BOOTSTRAP_OWNER_PASSWORD`（仅首次引导命令临时使用）

不得把真实值写入 `.env.example`、命令输出、日志、截图、验收记录或 Git。Cloudflare Access 两个 Header 仅由后端适配器构造。

## 首次部署

```bash
docker compose pull
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose ps
```

确认 `postgres`、`redis`、`minio`、`api` 为 healthy，`minio-init` 正常退出。然后按 README 的命令创建首个 owner。

## 反向代理与端口

生产环境只公开反向代理的 HTTPS 入口。不要假定 UFW 会自动拦截 Docker 发布端口；需要同时检查 Compose 监听地址、Docker NAT 铓和代理规则。PostgreSQL、Redis 与 MinIO 管理端口不应直接暴露公网。

## 升级与回滚

升级前备份数据库与对象存储。数据库迁移先在测试环境执行；应用镜像、迁移版本和 Git commit 必须对应。回滚时优先恢复上一镜像，并仅在已验证 Alembic downgrade 不丢数据时回退数据库；否则从备份恢复到独立实例后切换流量。
