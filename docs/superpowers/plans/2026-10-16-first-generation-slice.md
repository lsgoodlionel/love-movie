# 爱视频首个真实生成切片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个可通过 Docker Compose 运行的内部团队 Web 平台，让用户输入文字后真实调用远程 Ollama/ComfyUI 生成图片或视频，并持久化任务与素材供在线预览和下载。

**Architecture:** Next.js Web 只访问 FastAPI；FastAPI 将生成任务持久化到 PostgreSQL 并投递 Redis，独立 Python Worker 串行持有全局 GPU 租约，调用远程 Ollama/ComfyUI 后将输出转存到 MinIO。PostgreSQL 是任务状态权威来源，Redis 只负责队列、短期事件和租约，远端服务凭据只存在于后端 Secret/环境变量。

**Tech Stack:** Node.js 22、Next.js、TypeScript、React、Vitest、Playwright；Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、pytest、httpx、websockets、ARQ；PostgreSQL 16、Redis 7、MinIO、FFmpeg、Docker Compose。

**Spec:** `docs/superpowers/specs/2026-10-16-ai-video-studio-design.md`

## Global Constraints

- 用户界面、任务状态和可操作错误默认使用中文；代码标识与协议字段保持英文。
- 浏览器不得直接请求 Ollama 或 ComfyUI，也不得获得 Cloudflare Access Client ID/Secret。
- Cloudflare Access 凭据只从服务端环境变量或 Docker Secret 注入，禁止写入仓库、数据库、日志、响应或前端 bundle。
- Ollama 基址固定由 `OLLAMA_BASE_URL` 配置，当前验证值为 `https://openclaw.lsgood.cn`；ComfyUI 基址由 `COMFYUI_BASE_URL` 配置，当前验证值为 `https://comfyui.lsgood.cn`。
- 第一版重型 GPU 阶段全局并发必须为 `1`；Ollama 规划请求必须使用 `keep_alive: "0s"` 并在进入 ComfyUI 阶段前确认卸载。
- ComfyUI 只运行仓库内审核过的白名单模板；前端不得提交 workflow JSON。
- 尺寸、帧数、采样步数、批量数、提示词长度和文件大小必须由服务端硬限制，不能只依赖前端校验。
- ComfyUI 输出必须下载、校验并转存 MinIO；不得把 `/view` 临时 URL 保存为正式素材 URL。
- ComfyUI WebSocket 只提供实时进度，`GET /history/{prompt_id}` 是最终结果权威来源；Cloudflare `1033` 不代表 GPU 任务失败。
- 所有生成请求先持久化，再入队；`prompt_id` 收到后立即持久化；无法确认提交结果时不得盲目重复 `/prompt`。
- Ollama 模型路由、ComfyUI 工作流版本、远端节点和能力标签必须由后台配置资源管理，业务代码不得写死选择逻辑或服务器域名。
- 当前 Wan 1.3B 单镜头固定为约 5 秒能力边界；后续 30 秒短片必须采用 6×约 5 秒镜头和逐镜头审核/重试，不得尝试一次生成 30 秒。
- 内部版本也必须记录内容安全判断和成年人确认；任何涉及未成年人的性化内容在入队前拒绝，并按租户记录 GPU 秒数和存储用量。
- 只提交本项目文件；`.env`、Secret、生成素材和测试下载文件必须被 Git 忽略。

## Review Focus

- 浏览器或网络重试同一请求：Task 3 必须证明相同幂等键只创建一个任务，Task 7/8 必须证明不会重复提交远端作业。
- Worker 在获得 `prompt_id` 后崩溃：Task 6/7 必须证明重启后查询远端 history 并恢复，而不是再次调用 `/prompt`。
- 两个图片/视频任务同时到达：Task 6 必须证明 Ollama 与 ComfyUI 重型阶段不会并发占用 GPU。
- 用户尝试越权读取他人项目素材或提交超限参数：Task 2、4、9 必须证明返回 403/422 且不入队。
- 远端返回 Cloudflare `1033`、含凭据 HTML 或畸形 JSON：Task 5/6 必须证明日志和 API 错误均脱敏，已有 `prompt_id` 的任务查询 history/queue 而不重复提交。

---

## File Structure

```text
love-movie/
├── apps/web/                         # Next.js 中文 Web 客户端
│   ├── app/(auth)/login/
│   ├── app/(studio)/generate/
│   ├── app/(studio)/assets/
│   ├── components/generation/
│   ├── lib/api/
│   └── tests/
├── services/backend/                # FastAPI、领域模型、Worker 与适配器
│   ├── app/api/
│   ├── app/core/
│   ├── app/domain/
│   ├── app/integrations/
│   ├── app/services/
│   ├── app/workflows/
│   ├── app/worker/
│   ├── alembic/
│   └── tests/
├── e2e/                             # Playwright 真实浏览器流程
├── infra/                           # Docker、MinIO、FFmpeg 与运维配置
├── docs/                            # 规格、计划、部署和验收记录
├── docker-compose.yml
├── .env.example
└── README.md
```

本计划只交付单镜头真实闭环。它完成后分别创建两个后续计划：第一份实现视觉圣经、6×约 5 秒镜头、关键帧/抽帧审核、FFmpeg 合成和简化时间线；第二份实现作品/卷章/分集/场景/镜头层级、长文本分块索引、一致性检查和多节点能力调度。

## Task 1: 可运行的仓库基线与本地基础设施

**Files:**
- Create: `.gitignore`, `.env.example`, `README.md`, `docker-compose.yml`
- Create: `services/backend/pyproject.toml`, `services/backend/Dockerfile`, `services/backend/app/main.py`, `services/backend/app/core/config.py`
- Create: `services/backend/tests/test_health.py`, `services/backend/tests/test_secret_policy.py`
- Create: `apps/web/package.json`, `apps/web/Dockerfile`, `apps/web/app/layout.tsx`, `apps/web/app/page.tsx`
- Create: `infra/minio/create-buckets.sh`

**Interfaces:**
- Produces: `Settings` with database, Redis, object-storage and remote-service configuration; `GET /health/live`; Docker services named `web`, `api`, `worker`, `postgres`, `redis`, `minio`.

- [ ] **Step 1: Write failing backend configuration and health tests**

Add `test_health_live_returns_ok` and `test_settings_repr_hides_access_secret`; assert `/health/live` returns `{"status":"ok"}` and a configured secret never appears in `repr(settings)`.

- [ ] **Step 2: Run the focused tests and verify collection or import failure**

Run: `cd services/backend && uv run pytest tests/test_health.py tests/test_secret_policy.py -q`

Expected: FAIL because the application and `Settings` do not exist.

- [ ] **Step 3: Implement the minimal backend skeleton and configuration**

Define `Settings(BaseSettings)` in `app/core/config.py`; Secret fields use `SecretStr`. Define `create_app() -> FastAPI` and `/health/live` in `app/main.py`.

- [ ] **Step 4: Add the Next.js shell, Dockerfiles, Compose dependencies and ignored paths**

Compose health checks must gate API/Worker startup on PostgreSQL, Redis and MinIO. `.env.example` contains names and safe examples only; `.gitignore` excludes `.env*` except `.env.example`, MinIO data, generated media and test artifacts.

- [ ] **Step 5: Verify tests and Compose expansion**

Run: `cd services/backend && uv run pytest tests/test_health.py tests/test_secret_policy.py -q`

Run: `docker compose config --quiet`

Expected: tests PASS and Compose exits 0 without printing secrets.

- [ ] **Step 6: Commit the repository baseline**

```bash
git add .gitignore .env.example README.md docker-compose.yml services/backend apps/web infra/minio
git commit -m "chore: bootstrap ai video studio"
```

## Task 2: 内部账号、四级角色与项目权限

**Files:**
- Create: `services/backend/app/domain/identity/models.py`, `schemas.py`, `permissions.py`
- Create: `services/backend/app/api/auth.py`, `projects.py`, `dependencies.py`
- Create: `services/backend/app/core/security.py`
- Create: `services/backend/alembic/versions/0001_identity_projects.py`
- Create: `services/backend/app/cli/bootstrap_owner.py`
- Test: `services/backend/tests/domain/test_permissions.py`, `services/backend/tests/api/test_auth_projects.py`

**Interfaces:**
- Consumes: `Settings` from Task 1.
- Produces: `Role = OWNER|ADMIN|CREATOR|REVIEWER`; `require_project_role(project_id, allowed_roles)`; session-cookie login; models `Tenant`, `User`, `Membership`, `Project`, `ProjectMember`.

- [ ] **Step 1: Write failing role and tenant-isolation tests**

Assert reviewers cannot create generation work; creators can; a user from tenant A receives 403 for tenant B's project; disabled users cannot log in.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd services/backend && uv run pytest tests/domain/test_permissions.py tests/api/test_auth_projects.py -q`

- [ ] **Step 3: Implement identity models, migration and password/session security**

Use UUID primary keys, Argon2 password hashes, HttpOnly/Secure/SameSite=Lax session cookies and server-side session revocation. `bootstrap_owner` reads credentials from process environment without logging them.

- [ ] **Step 4: Implement auth/project endpoints and permission dependencies**

Provide `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`, `POST /api/v1/projects`, `GET /api/v1/projects`.

- [ ] **Step 5: Run migration and permission tests**

Run: `cd services/backend && uv run alembic upgrade head && uv run pytest tests/domain/test_permissions.py tests/api/test_auth_projects.py -q`

Expected: PASS, including cross-tenant 403 cases.

- [ ] **Step 6: Commit identity and permissions**

```bash
git add services/backend/app services/backend/alembic services/backend/tests
git commit -m "feat: add internal identity and project roles"
```

## Task 3: 任务、步骤、素材和幂等领域模型

**Files:**
- Create: `services/backend/app/domain/generation/models.py`, `schemas.py`, `state_machine.py`, `repository.py`
- Create: `services/backend/app/domain/assets/models.py`, `schemas.py`
- Create: `services/backend/alembic/versions/0002_generation_assets.py`
- Test: `services/backend/tests/domain/test_generation_state.py`, `test_idempotency.py`, `test_asset_lineage.py`

**Interfaces:**
- Consumes: tenant/user/project identifiers from Task 2.
- Produces: `GenerationKind = IMAGE|VIDEO`; `GenerationStatus`; `GenerationTask`, `GenerationStep`, `Asset`, `UsageLedger`; `create_or_get_task(command, idempotency_key) -> (GenerationTask, bool)`.

- [ ] **Step 1: Write failing state-transition, idempotency and lineage tests**

Assert invalid transitions raise `InvalidTransition`; two concurrent inserts with the same tenant and idempotency key return one task; a video asset can reference the generated first-frame asset and originating task；usage/audit rows retain requested model, actual model, GPU seconds, content-safety decision and adult-content declaration without storing credentials.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd services/backend && uv run pytest tests/domain/test_generation_state.py tests/domain/test_idempotency.py tests/domain/test_asset_lineage.py -q`

- [ ] **Step 3: Implement models, database uniqueness and state machine**

Enforce unique `(tenant_id, idempotency_key)`. Store status, current step, attempt count, `remote_prompt_id`, sanitized error code, timing, parameters, workflow version and cancellation timestamp.

- [ ] **Step 4: Implement repository transaction semantics**

`create_or_get_task` must handle the uniqueness race by rolling back and loading the winner; it returns `created=False` for duplicates.

- [ ] **Step 5: Apply migration and run domain tests**

Run: `cd services/backend && uv run alembic upgrade head && uv run pytest tests/domain/test_generation_state.py tests/domain/test_idempotency.py tests/domain/test_asset_lineage.py -q`

- [ ] **Step 6: Commit the generation domain**

```bash
git add services/backend/app/domain services/backend/alembic services/backend/tests/domain
git commit -m "feat: model generation tasks and assets"
```

## Task 4: 后台 AI 资源、白名单工作流与参数硬限制

**Files:**
- Create: `services/backend/app/domain/ai_resources/models.py`, `schemas.py`, `repository.py`
- Create: `services/backend/app/workflows/registry.py`, `model_router.py`, `policies.py`, `exceptions.py`
- Create: `services/backend/app/workflows/templates/z_image_turbo_v1.json`
- Create: `services/backend/app/workflows/templates/wan_i2v_v1.json`
- Create: `services/backend/alembic/versions/0003_ai_resources.py`
- Test: `services/backend/tests/workflows/test_registry.py`, `test_model_router.py`, `test_parameter_policy.py`, `test_template_injection.py`

**Interfaces:**
- Produces: models `ComputeNode`, `WorkflowDefinition`, `ModelRoute`; `WorkflowRegistry.get(name, version) -> WorkflowTemplate`; `ModelRouter.select(capability, quality) -> ModelSelection`; `render_image_workflow(ImageParameters) -> dict`; `render_video_workflow(VideoParameters, uploaded_image_name) -> dict`.

- [ ] **Step 1: Write failing allowlist and limit tests**

Assert unknown workflows are rejected; arbitrary JSON is never accepted; prompt length, width, height, steps, frame count, batch size, per-tenant GPU seconds and storage usage over server limits produce field-specific validation errors before queueing. Assert sexualized-minor content is rejected before queueing and adult-content requests require an explicit adult declaration. Assert the default model route is `qwen3.5:4b` for cleanup/JSON repair, `qwen3.5:latest` for story/shot planning and `gemma4:12b` for dialogue enhancement; 27B/31B routes require asynchronous high-quality or explicit manual mode.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd services/backend && uv run pytest tests/workflows -q`

- [ ] **Step 3: Import and sanitize the two verified workflow structures**

Use the checksum-verified `/Users/lionel/Develop/comfyui-api-handoff/z-image-bedroom-api.json` and `wan-bedroom-video-api.json` only as structural sources. Replace example prompts, input filenames, seeds and output prefixes with runtime-injected values; remove the synchronous WebP output from the production video template; keep reviewed model/node topology and assign immutable version `v1`.

- [ ] **Step 4: Implement configurable resources, model routing and deterministic template injection**

Seed remote nodes, workflow metadata and model routes into database resources without secrets. Normal-user defaults and maxima live in `policies.py`; the API may expose allowed choices but cannot override maxima. Template rendering deep-copies the source and only changes declared node/input paths. Record requested model, actual model and fallback reason.

- [ ] **Step 5: Run workflow tests and snapshot rendered node changes**

Run: `cd services/backend && uv run pytest tests/workflows -q`

Expected: PASS and snapshots prove no undeclared node changed.

- [ ] **Step 6: Commit reviewed workflows and policies**

```bash
git add services/backend/app/domain/ai_resources services/backend/app/workflows services/backend/alembic services/backend/tests/workflows
git commit -m "feat: configure ai resources and workflows"
```

## Task 5: Ollama、ComfyUI 与对象存储适配器

**Files:**
- Create: `services/backend/app/integrations/access_headers.py`, `ollama.py`, `comfyui.py`, `storage.py`, `errors.py`, `redaction.py`
- Test: `services/backend/tests/integrations/test_ollama.py`, `test_comfyui.py`, `test_storage.py`, `test_redaction.py`

**Interfaces:**
- Consumes: enabled `ComputeNode` and `ModelRoute` records from Task 4; Access Secret remains environment-only.
- Produces: `OllamaAdapter.plan_video_text(request) -> PlannedPrompts`; `OllamaAdapter.wait_until_unloaded(timeout) -> None`; `ComfyUIAdapter.submit(workflow, client_id) -> prompt_id`; `track(prompt_id) -> AsyncIterator[ProgressEvent]`; `download_output(output) -> AsyncIterator[bytes]`; `StorageAdapter.put_stream(...) -> StoredObject` and `presign_get(key, ttl_seconds=300) -> str`.

- [ ] **Step 1: Write failing adapter contract and redaction tests**

Use mocked HTTP/WS servers. Assert both Access headers are attached server-side, `keep_alive` is exactly `0s`, `prompt_id` is parsed, WS failure falls back to authoritative history polling, and secrets/HTML/malformed payloads never appear in raised public errors or captured logs. Cover Access 401/403, Cloudflare `1033`, ComfyUI validation error, OOM, remote soft timeout, interrupted download and storage failure as distinct stable error codes.

- [ ] **Step 2: Run integration tests and verify failure**

Run: `cd services/backend && uv run pytest tests/integrations -q`

- [ ] **Step 3: Implement shared access headers, timeouts and error normalization**

Secrets remain `SecretStr` until header construction. Define bounded connect/read timeouts and map remote failures to stable codes such as `REMOTE_AUTH_FAILED`, `REMOTE_TIMEOUT`, `REMOTE_INVALID_RESPONSE`.

- [ ] **Step 4: Implement Ollama and ComfyUI clients**

ComfyUI tracking prefers WebSocket `/ws?clientId=...` for progress, reconnects with a bound, and always uses `/history/{prompt_id}` as the final result authority. `1033` triggers bounded backoff and later history/queue reconciliation, never an implicit second `/prompt` submission.

- [ ] **Step 5: Implement streaming object storage and integrity checks**

Check content type, declared/actual size limits and SHA-256 while streaming; never buffer a full video solely for storage.

- [ ] **Step 6: Run integration tests**

Run: `cd services/backend && uv run pytest tests/integrations -q`

Expected: PASS, including malformed and secret-redaction cases.

- [ ] **Step 7: Commit integration adapters**

```bash
git add services/backend/app/integrations services/backend/tests/integrations
git commit -m "feat: add secure remote service adapters"
```

## Task 6: Redis 队列、单 GPU 租约与恢复协调器

**Files:**
- Create: `services/backend/app/worker/settings.py`, `queue.py`, `gpu_lease.py`, `runner.py`, `recovery.py`
- Create: `services/backend/app/services/generation_dispatcher.py`
- Test: `services/backend/tests/worker/test_gpu_lease.py`, `test_dispatch.py`, `test_recovery.py`

**Interfaces:**
- Consumes: `GenerationTask` from Task 3 and remote adapters from Task 5.
- Produces: `enqueue_generation(task_id) -> job_id`; async context manager `GpuLease.acquire(task_id)`; `recover_incomplete_tasks() -> RecoveryReport`.

- [ ] **Step 1: Write failing concurrency and crash-recovery tests**

Start two competing async jobs and assert peak lease holders equals one. Simulate a task with persisted `remote_prompt_id` and assert recovery calls history tracking but not `submit`.

- [ ] **Step 2: Run worker tests and verify failure**

Run: `cd services/backend && uv run pytest tests/worker -q`

- [ ] **Step 3: Implement ARQ enqueueing with stable job IDs**

Use the generation task UUID as the ARQ job ID. A duplicate enqueue returns the existing job and does not create another database task.

- [ ] **Step 4: Implement renewable Redis GPU lease**

Use an owner token, finite TTL, heartbeat renewal and compare-and-delete release. Loss of ownership stops the next remote step and records `GPU_LEASE_LOST`.

- [ ] **Step 5: Implement startup recovery decisions**

Queued tasks are re-enqueued；tasks with `remote_prompt_id` first query history, then queue, and resume tracking；tasks whose submission outcome is unknown move to `NEEDS_ATTENTION`；completed/cancelled tasks are untouched. A persisted `1033` error alone never authorizes resubmission.

- [ ] **Step 6: Run worker tests**

Run: `cd services/backend && uv run pytest tests/worker -q`

Expected: PASS, including peak concurrency of one and no duplicate `/prompt` after recovery.

- [ ] **Step 7: Commit queue and recovery coordination**

```bash
git add services/backend/app/worker services/backend/app/services/generation_dispatcher.py services/backend/tests/worker
git commit -m "feat: add single gpu generation queue"
```

## Task 7: 图片生成纵向切片

**Files:**
- Create: `services/backend/app/services/image_generation.py`
- Create: `services/backend/app/api/generations.py`
- Test: `services/backend/tests/services/test_image_generation.py`, `services/backend/tests/api/test_create_image.py`

**Interfaces:**
- Consumes: permissions, task repository, workflow registry, queue, ComfyUI and storage adapters.
- Produces: `POST /api/v1/generations/images`; `ImageGenerationService.run(task_id) -> Asset`; persisted step progress and usage ledger.

- [ ] **Step 1: Write failing API, idempotency and service tests**

Assert a creator receives 202 with one task ID; repeating the same `Idempotency-Key` returns the same ID; reviewer or over-limit parameters return 403/422 without enqueueing; success persists `prompt_id` before tracking and stores a platform object key.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd services/backend && uv run pytest tests/services/test_image_generation.py tests/api/test_create_image.py -q`

- [ ] **Step 3: Implement the image endpoint and transactional dispatch**

Define request/response schemas with Chinese error messages. Commit the task before enqueueing; if queue publication fails, mark `DISPATCH_FAILED` for safe retry.

- [ ] **Step 4: Implement the image service state transitions**

Acquire the GPU lease, render the allowlisted workflow, submit once, persist `prompt_id`, track, download, validate, store, create asset/usage rows and release the lease.

- [ ] **Step 5: Run image slice tests**

Run: `cd services/backend && uv run pytest tests/services/test_image_generation.py tests/api/test_create_image.py -q`

Expected: PASS and no test path can issue two `submit` calls for one task.

- [ ] **Step 6: Commit the image slice**

```bash
git add services/backend/app/services/image_generation.py services/backend/app/api/generations.py services/backend/tests
git commit -m "feat: generate and persist images"
```

## Task 8: 模型路由、首帧与单镜头图生视频纵向切片

**Files:**
- Create: `services/backend/app/services/video_generation.py`, `planning.py`
- Test: `services/backend/tests/services/test_video_generation.py`, `test_planning.py`
- Modify: `services/backend/app/api/generations.py`

**Interfaces:**
- Consumes: image workflow, video workflow, Ollama/ComfyUI/storage adapters and GPU lease.
- Produces: `POST /api/v1/generations/videos`; `VideoGenerationService.run(task_id) -> Asset`; lineage `text -> first_frame -> video`.

- [ ] **Step 1: Write failing video orchestration tests**

Assert exact order: select configured planning model, Ollama plan with `keep_alive: "0s"`, unload confirmation, image submit, first-frame persist, collision-safe image upload, video submit, video persist. Assert Ollama unload timeout prevents ComfyUI submission and two stages each persist their own `prompt_id` before tracking. Assert upload names include tenant/project/task plus a random suffix and use `overwrite=false`.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd services/backend && uv run pytest tests/services/test_planning.py tests/services/test_video_generation.py -q`

- [ ] **Step 3: Implement structured planning schema and validation**

`PlannedPrompts` contains `image_prompt`, `motion_prompt`, `negative_prompt` and `title`; reject missing or oversized fields before GPU generation. Use configured default `qwen3.5:latest` for story/shot planning and `qwen3.5:4b` for prompt cleanup/JSON repair, with schema validation after every model response.

- [ ] **Step 4: Implement video endpoint and orchestration**

Persist the Ollama plan, requested/actual model, fallback reason, first-frame asset and final video as separate lineage records. Use one task with recoverable steps and never hide a successful first frame when video generation fails. Enforce the verified single-shot policy of 512×512, 81 frames, 16 FPS, 20 steps and an allowed camera-pose enum; longer videos belong to the successor multi-shot plan.

- [ ] **Step 5: Run video slice tests**

Run: `cd services/backend && uv run pytest tests/services/test_planning.py tests/services/test_video_generation.py -q`

Expected: PASS, including unload timeout and crash boundaries.

- [ ] **Step 6: Commit the video slice**

```bash
git add services/backend/app/services services/backend/app/api/generations.py services/backend/tests/services
git commit -m "feat: generate videos from text"
```

## Task 9: 任务查询、进度事件、取消与素材访问

**Files:**
- Create: `services/backend/app/api/tasks.py`, `assets.py`, `events.py`
- Create: `services/backend/app/services/cancellation.py`, `progress.py`
- Test: `services/backend/tests/api/test_tasks.py`, `test_assets.py`, `test_cancellation.py`, `test_progress.py`

**Interfaces:**
- Produces: `GET /api/v1/tasks/{id}`; `GET /api/v1/tasks/{id}/events` as SSE; `POST /api/v1/tasks/{id}/cancel`; `GET /api/v1/assets`; `POST /api/v1/assets/{id}/access` returning a 300-second URL.

- [ ] **Step 1: Write failing ownership, progress and cancellation tests**

Assert cross-project access is 403; SSE reconnect with `Last-Event-ID` resumes without duplicates; queued cancellation prevents execution; running cancellation reaches a terminal state; access URLs expire after 300 seconds.

- [ ] **Step 2: Run API tests and verify failure**

Run: `cd services/backend && uv run pytest tests/api/test_tasks.py tests/api/test_assets.py tests/api/test_cancellation.py tests/api/test_progress.py -q`

- [ ] **Step 3: Implement authorized task and asset queries**

Every repository query accepts tenant and project scope. Responses expose sanitized codes and Chinese messages, never raw remote bodies or internal object keys unless required for authorized access signing.

- [ ] **Step 4: Implement durable progress replay and cancellation**

Persist progress milestones in PostgreSQL; Redis accelerates live delivery. SSE reconnect first replays database events, then subscribes. Cancellation records intent before touching the queue or remote service.

- [ ] **Step 5: Run API tests**

Run: `cd services/backend && uv run pytest tests/api/test_tasks.py tests/api/test_assets.py tests/api/test_cancellation.py tests/api/test_progress.py -q`

- [ ] **Step 6: Commit task and asset APIs**

```bash
git add services/backend/app/api services/backend/app/services services/backend/tests/api
git commit -m "feat: expose generation history and assets"
```

## Task 10: 中文快速生成台与素材预览

**Files:**
- Create: `apps/web/app/(auth)/login/page.tsx`
- Create: `apps/web/app/(studio)/layout.tsx`, `generate/page.tsx`, `assets/page.tsx`
- Create: `apps/web/components/generation/GenerationForm.tsx`, `TaskProgress.tsx`, `ResultPreview.tsx`, `RecentTasks.tsx`
- Create: `apps/web/lib/api/client.ts`, `auth.ts`, `generations.ts`, `tasks.ts`, `assets.ts`
- Test: `apps/web/tests/generation-form.test.tsx`, `task-progress.test.tsx`, `result-preview.test.tsx`

**Interfaces:**
- Consumes: auth, generation, task-event and asset endpoints from Tasks 2, 7, 8 and 9.
- Produces: login flow; image/video form; reconnecting progress UI; image and HTML5 video preview; download and regenerate actions.

- [ ] **Step 1: Write failing UI tests**

Assert Chinese labels, image/video mode selection, disabled duplicate submit, field-level 422 display, task-state translation, SSE reconnect banner, image preview and `<video controls>` rendering.

- [ ] **Step 2: Run UI tests and verify failure**

Run: `cd apps/web && npm test -- --run`

- [ ] **Step 3: Implement typed API client and authentication shell**

Use same-origin `/api` proxying and cookie credentials. The client must not define Ollama/ComfyUI URLs or Cloudflare Access headers.

- [ ] **Step 4: Implement the two-column quick generation page**

Left: prompt, kind, aspect ratio, seed and allowed advanced parameters. Right: current status, sanitized failure, preview, download and regenerate. Bottom: recent tasks.

- [ ] **Step 5: Implement progress reconnect and asset previews**

SSE disconnect shows “正在重新连接”，then resumes with the last event ID; page reload fetches the current task before subscribing.

- [ ] **Step 6: Run unit, type and production build checks**

Run: `cd apps/web && npm test -- --run`

Run: `cd apps/web && npm run typecheck && npm run build`

Expected: all PASS; build output contains no remote AI hostname or Access header name.

- [ ] **Step 7: Commit the Web generation studio**

```bash
git add apps/web
git commit -m "feat: add web generation studio"
```

## Task 11: 端到端、恢复验证、管理诊断与交付文档

**Files:**
- Create: `e2e/playwright.config.ts`, `e2e/generation.spec.ts`, `e2e/recovery.spec.ts`
- Create: `services/backend/app/api/admin_health.py`, `admin_ai_resources.py`
- Test: `services/backend/tests/api/test_admin_health.py`, `test_admin_ai_resources.py`
- Create: `docs/deployment.md`, `docs/operations.md`, `docs/acceptance/first-generation-slice.md`
- Modify: `README.md`, `docker-compose.yml`

**Interfaces:**
- Produces: owner/admin-only `GET /api/v1/admin/health`; CRUD/enable/disable endpoints for compute nodes, workflow metadata and model routes that never accept or return Access Secret; documented local startup, secret injection, backup, recovery and remote smoke procedures.

- [ ] **Step 1: Write failing admin-health and browser tests**

Admin health must report component state without secrets; resource API tests prove reviewers/creators receive 403, administrators can change route priority and enable state, and no response accepts or returns credential fields. Browser flow covers login, image creation, refresh recovery, preview, download and single-shot video creation using deterministic adapter fakes.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd services/backend && uv run pytest tests/api/test_admin_health.py -q`

Run: `cd e2e && npx playwright test`

- [ ] **Step 3: Implement admin health and deterministic E2E adapter mode**

Fake mode is allowed only when `APP_ENV=test`; production startup fails if fake adapters are requested. Health output includes PostgreSQL, Redis, MinIO, Worker, Ollama and ComfyUI status plus queue length and current lease task ID. Implement resource administration as metadata/configuration only; Service Token values remain environment-only.

- [ ] **Step 4: Add recovery and concurrency browser/API scenarios**

Test browser refresh, duplicate Idempotency-Key, two simultaneous jobs, Worker restart with persisted `prompt_id`, Cloudflare `1033`, Access denial, OOM, remote timeout and cross-project asset denial. For every post-submit fault, assert history/queue reconciliation occurs before any retry decision.

- [ ] **Step 5: Document deployment and secret handling**

Document how operators inject `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` without recording values. Include initial owner bootstrap, migrations, object-storage initialization, health checks, backups and rollback.

- [ ] **Step 6: Run the complete local acceptance suite**

Run: `docker compose up -d --build`

Run: `docker compose exec api pytest -q`

Run: `cd apps/web && npm test -- --run && npm run typecheck && npm run build`

Run: `cd e2e && npx playwright test`

Expected: all suites PASS; `docker compose ps` reports healthy core services.

- [ ] **Step 7: Run the controlled remote smoke test**

Inject the existing website Service Token into the backend process without echoing it. Generate one minimal image and one 81-frame video; verify Ollama `/api/tags` and ComfyUI `/system_stats` health, strict GPU serialization, requested/actual model audit, authoritative history lookup, platform-owned object keys, ffprobe decode metadata, browser playback and absence of credentials in logs.

- [ ] **Step 8: Record sanitized acceptance evidence and update project status**

Write command, commit, environment, workflow version, task IDs, timings and pass/fail summary to `docs/acceptance/first-generation-slice.md`; do not include prompts containing private text, Access headers, Secret values or raw remote logs.

- [ ] **Step 9: Commit the verified delivery**

```bash
git add README.md docker-compose.yml e2e services/backend/app/api/admin_health.py services/backend/app/api/admin_ai_resources.py services/backend/tests/api/test_admin_health.py services/backend/tests/api/test_admin_ai_resources.py docs/deployment.md docs/operations.md docs/acceptance
git commit -m "test: verify first generation slice"
```

## Final Gate

- [ ] Run `git status --short` and confirm only intended files are present.
- [ ] Run backend unit/integration tests, frontend unit/type/build checks and Playwright E2E at the final commit.
- [ ] Run one final real image and video acceptance only after local tests pass.
- [ ] Confirm repository and built frontend contain no Service Token, `.env`, private prompt or generated media.
- [ ] Update README and the existing acceptance record with final commands and sanitized outcomes.
- [ ] Read `/Users/lionel/.codex/memories/claude-code-migration/github-repositories.md` before any push. If this project still has no registered GitHub remote, stop after local commits and report that no push was attempted.
- [ ] After a registered push, update the corresponding Obsidian project overview with date, branch, commit, tests, completed scope, remaining issues and GitHub traceability.
