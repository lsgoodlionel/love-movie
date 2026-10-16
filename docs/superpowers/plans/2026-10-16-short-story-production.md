# 短故事配音字幕视频生产链 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有文字生成图片/单镜头视频闭环上，交付“短故事 → 可审阅分镜 → 六个约 5 秒镜头 → 中文配音与字幕 → 简化时间线 → MP4 成片”的 Web 生产链，并让后续小说分集流程复用同一套内容与素材模型。

**Architecture:** 保持 Next.js + FastAPI 模块化单体和 ARQ Worker 架构，在 PostgreSQL 中增加作品、版本、角色/场景/风格卡、场景、镜头、台词、字幕和时间线模型。Ollama 只生成版本化结构化规划；用户批准分镜和关键帧后，现有 GenerationTask/Asset 流程逐镜头消费 GPU；独立 media-worker 负责 FFmpeg/ffprobe、TTS、字幕和成片合成，不占 GPU 租约。

**Tech Stack:** Next.js 16、React 19、TypeScript、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、ARQ、PostgreSQL、Redis、MinIO、Ollama、ComfyUI、FFmpeg/ffprobe、可替换 TTS Provider（首个实现为 Edge TTS）、Pytest、Vitest、Playwright。

**Spec:** `docs/superpowers/specs/2026-10-16-ai-video-studio-design.md`

## Global Constraints

- 中文 UI、业务状态和可操作错误；代码标识和协议字段保持英文。
- 内容层级固定为 `作品 -> 版本 -> 分集 -> 场景 -> 镜头 -> 生成任务 -> 素材版本`，短故事也使用该层级，不另建一次性模型。
- 30 秒标准短片固定为 6 个约 5 秒镜头；单镜头继续使用 512×512、81 帧、16 FPS、20 steps 的已审核工作流。
- 用户批准分镜前不得提交图片或视频 GPU 任务；关键帧批准前不得提交对应镜头视频任务。
- Ollama 规划请求使用 `keep_alive: "0s"`，并保存请求模型、实际模型、回退原因、模板版本和 Schema 版本。
- 浏览器不得接触 Ollama、ComfyUI、TTS Provider 或 Cloudflare Access 凭据。
- 语音能力通过 Provider 接口接入；Provider 未配置时必须显示“未配置”并阻止合成，不得生成空白音轨冒充配音。
- media-worker 不持有 GPU 租约；所有媒体输入先从平台对象存储下载，输出校验后再写回平台对象存储。
- 合成前统一分辨率、FPS、SAR、色彩空间和 `yuv420p`；成片必须通过 ffprobe 可解码性与时长校验。
- 多租户、项目成员权限、幂等、配额预留、取消、恢复和敏感信息过滤继续沿用首个切片规则。
- 不实现任意多轨、复杂关键帧动画、数字人、自动批量生成整部小说或未经审阅的持续 GPU 消耗。

## Review Focus

- Ollama 返回缺字段、重复镜头 ID、总时长超限或无法解析 JSON：规划任务应进入可修订失败状态，不创建半成品镜头，也不消耗 GPU。
- 两个浏览器标签同时批准同一分镜或关键帧：只能产生一组镜头/一项生成任务，重复请求返回同一资源。
- 用户修改已批准分镜：创建新作品版本并标记旧素材来源，不得静默改写已生成镜头的输入。
- media-worker 在合成中途重启或重复消费：相同 timeline revision 只产生一个有效 render，已完成镜头和音频不得重复生成。
- 某个镜头、TTS 或字幕失败：成片保持不可导出并明确指出失败项，其他合格镜头可继续预览、替换和独立重试。

---

## File Structure

```text
services/backend/app/
├── domain/production/        # 作品层级、视觉圣经、镜头、台词、时间线、成片
├── api/productions.py        # 作品、版本、规划、批准、镜头与时间线 API
├── services/story_planning.py
├── services/shot_generation.py
├── services/timeline_render.py
├── integrations/tts/         # Provider 协议、Edge TTS、禁用态
└── media/                     # FFmpeg 命令构建、探测、字幕与 QC
apps/web/
├── app/(studio)/productions/
├── components/production/
└── lib/api/productions.ts
```

## Task 1: 可版本化作品、视觉圣经和镜头领域模型

**Files:**
- Create: `services/backend/app/domain/production/models.py`
- Create: `services/backend/app/domain/production/schemas.py`
- Create: `services/backend/app/domain/production/repository.py`
- Create: `services/backend/alembic/versions/0009_short_story_production.py`
- Test: `services/backend/tests/domain/test_production_hierarchy.py`
- Test: `services/backend/tests/domain/test_production_versioning.py`

**Interfaces:**
- Consumes: `Tenant`, `Project`, `User`, `GenerationTask`, `Asset`。
- Produces: `Production`, `ProductionVersion`, `Episode`, `Scene`, `Shot`, `CharacterCard`, `LocationCard`, `StyleBible`, `DialogueLine`, `SubtitleCue`, `Timeline`, `TimelineClip`, `Render`; `ProductionRepository.create_version(...)`; `approve_storyboard(...)`; `revise_from(version_id) -> ProductionVersion`。

- [ ] **Step 1: Write failing hierarchy and versioning tests**

覆盖租户/项目外键、短故事默认单集、场景与镜头稳定排序、六镜头总时长约 30 秒、批准后的内容不可原地改写、修订创建新版本并保留来源版本。

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd services/backend && uv run pytest tests/domain/test_production_hierarchy.py tests/domain/test_production_versioning.py -q`

Expected: FAIL because `app.domain.production` and migration `0009` do not exist.

- [ ] **Step 3: Implement models, schemas, repository transactions and migration**

镜头保存 `order_index`、目标时长、景别、机位、动作、视觉提示词、旁白/对白引用、批准状态、关键帧/视频当前素材 ID；版本状态使用 `draft|planned|storyboard_approved|keyframes_approved|render_ready|completed`。

- [ ] **Step 4: Apply migration and verify GREEN**

Run: `cd services/backend && uv run alembic upgrade head && uv run pytest tests/domain/test_production_hierarchy.py tests/domain/test_production_versioning.py -q`

Expected: PASS and `uv run alembic check` reports no new operations.

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/domain/production services/backend/alembic/versions/0009_short_story_production.py services/backend/tests/domain
git commit -m "feat: model versioned short story productions"
```

## Task 2: Ollama 结构化剧本、分镜和视觉圣经规划

**Files:**
- Modify: `services/backend/app/integrations/ollama.py`
- Create: `services/backend/app/services/story_planning.py`
- Create: `services/backend/app/prompts/short_story_v1.py`
- Test: `services/backend/tests/integrations/test_ollama_structured.py`
- Test: `services/backend/tests/services/test_story_planning.py`

**Interfaces:**
- Consumes: `ModelRouter.select("story_planning", "interactive", tenant_id)`、`ProductionRepository`。
- Produces: `OllamaAdapter.generate_structured(request: StructuredRequest[T]) -> StructuredResult[T]`; `ShortStoryPlan`; `StoryPlanningService.plan(version_id, source_text) -> ProductionVersion`。

- [ ] **Step 1: Write failing structured-output and atomic-plan tests**

覆盖正确六镜头计划、缺字段、重复镜头编号、时长总和不在 27–33 秒、模型返回 Markdown 包裹 JSON、JSON 修复仍失败，以及失败时数据库中不出现部分场景/镜头。

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd services/backend && uv run pytest tests/integrations/test_ollama_structured.py tests/services/test_story_planning.py -q`

- [ ] **Step 3: Implement versioned prompt/schema and generic structured adapter**

`ShortStoryPlan` 包含标题、梗概、角色卡、地点卡、风格卡、单集、场景和严格六镜头；每镜头包含旁白、对白、动作、景别、机位、目标时长、image_prompt、motion_prompt、negative_prompt。

- [ ] **Step 4: Persist the plan atomically with audit metadata**

保存 `prompt_template_version=short_story_v1`、`schema_version=1`、requested/actual model、fallback reason 和耗时；完整用户原文不进入普通日志。

- [ ] **Step 5: Verify GREEN and full backend suite**

Run: `cd services/backend && uv run pytest tests/integrations/test_ollama_structured.py tests/services/test_story_planning.py -q && uv run pytest -q`

- [ ] **Step 6: Commit**

```bash
git add services/backend/app/integrations/ollama.py services/backend/app/services/story_planning.py services/backend/app/prompts services/backend/tests
git commit -m "feat: plan structured short story storyboards"
```

## Task 3: 作品规划、审阅和批准 API

**Files:**
- Create: `services/backend/app/api/productions.py`
- Modify: `services/backend/app/main.py`
- Test: `services/backend/tests/api/test_productions.py`
- Test: `services/backend/tests/api/test_storyboard_approval.py`

**Interfaces:**
- Produces: `POST /api/v1/productions`; `POST /{id}/versions`; `POST /versions/{id}/plan`; `GET /versions/{id}`; `PATCH /shots/{id}`; `POST /versions/{id}/approve-storyboard`。

- [ ] **Step 1: Write failing API permission, idempotency and approval tests**

验证 reviewer 只读、跨租户 403、重复 plan/approve 返回同一版本、批准前无 GenerationTask、批准后修改镜头返回 409 并提示创建新版本。

- [ ] **Step 2: Run tests and verify RED**

Run: `cd services/backend && uv run pytest tests/api/test_productions.py tests/api/test_storyboard_approval.py -q`

- [ ] **Step 3: Implement scoped endpoints and optimistic revision checks**

所有写操作要求 `If-Match` 版本号或幂等键；冲突返回中文 409，不覆盖其他编辑者的修改。

- [ ] **Step 4: Verify GREEN and API schema**

Run: `cd services/backend && uv run pytest tests/api/test_productions.py tests/api/test_storyboard_approval.py -q`

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/api/productions.py services/backend/app/main.py services/backend/tests/api
git commit -m "feat: expose storyboard review workflow"
```

## Task 4: 关键帧批量生成、批准和逐镜头视频复用

**Files:**
- Create: `services/backend/app/services/shot_generation.py`
- Modify: `services/backend/app/worker/runner.py`
- Modify: `services/backend/app/worker/recovery.py`
- Modify: `services/backend/app/api/productions.py`
- Test: `services/backend/tests/services/test_shot_generation.py`
- Test: `services/backend/tests/worker/test_story_recovery.py`
- Test: `services/backend/tests/api/test_shot_generation.py`

**Interfaces:**
- Consumes: existing `GenerationRepository`, `ImageGenerationService`, `VideoGenerationService`, `GpuLease`。
- Produces: `ShotGenerationService.queue_keyframes(version_id)`; `approve_keyframe(shot_id, asset_id)`; `queue_shot_videos(version_id)`; stable per-shot idempotency keys derived from version/shot/input revision。

- [ ] **Step 1: Write failing approval-gate, duplicate-click and recovery tests**

验证未批准分镜不能生成关键帧、未批准关键帧不能生成视频、六镜头任务严格串行、单镜头失败可独立重试、Worker 重启复用已有 prompt_id/素材且不重复提交。

- [ ] **Step 2: Run tests and verify RED**

Run: `cd services/backend && uv run pytest tests/services/test_shot_generation.py tests/worker/test_story_recovery.py tests/api/test_shot_generation.py -q`

- [ ] **Step 3: Implement shot-to-generation linkage and batch orchestration**

关键帧与镜头视频仍是普通 GenerationTask/Asset；Shot 只保存当前选择和来源引用。队列按镜头顺序提交，但 GPU 租约仍是全局并发 1。

- [ ] **Step 4: Verify GREEN and existing recovery suite**

Run: `cd services/backend && uv run pytest tests/services/test_shot_generation.py tests/worker/test_story_recovery.py tests/api/test_shot_generation.py tests/worker -q`

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/services/shot_generation.py services/backend/app/worker services/backend/app/api/productions.py services/backend/tests
git commit -m "feat: generate approved storyboard shots"
```

## Task 5: FFmpeg/ffprobe 镜头质量检查和 media-worker

**Files:**
- Create: `services/backend/app/media/probe.py`
- Create: `services/backend/app/media/frames.py`
- Create: `services/backend/app/media/normalization.py`
- Create: `services/backend/app/worker/media_runtime.py`
- Create: `services/backend/app/worker/media_settings.py`
- Modify: `services/backend/Dockerfile`
- Modify: `docker-compose.yml`
- Test: `services/backend/tests/media/test_probe.py`
- Test: `services/backend/tests/media/test_frame_sampling.py`
- Test: `services/backend/tests/worker/test_media_jobs.py`

**Interfaces:**
- Produces: `probe_video(path) -> VideoProbe`; `sample_review_frames(path, policy) -> list[FrameSample]`; `normalize_clip(input, output, profile)`; ARQ queue `media` with stable job IDs。

- [ ] **Step 1: Write failing probe, sampling and idempotent media-job tests**

使用小型仓库内生成夹具，验证首/中/末帧、错误帧率/像素格式拒绝、损坏 MP4 拒绝、重复 media job 不产生多个 Render。

- [ ] **Step 2: Run tests and verify RED**

Run: `cd services/backend && uv run pytest tests/media tests/worker/test_media_jobs.py -q`

- [ ] **Step 3: Install FFmpeg and implement argument-list based subprocess wrappers**

禁止 `shell=True`；文件名、字幕和用户文本不得拼接为 shell 命令。标准输出为 512×512、16 FPS、SAR 1:1、BT.709、`yuv420p`、H.264/AAC MP4。

- [ ] **Step 4: Add independent media-worker service and verify it never acquires GpuLease**

Run: `docker compose config --quiet && cd services/backend && uv run pytest tests/media tests/worker/test_media_jobs.py -q`

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/media services/backend/app/worker/media_runtime.py services/backend/app/worker/media_settings.py services/backend/Dockerfile docker-compose.yml services/backend/tests
git commit -m "feat: add media quality and processing worker"
```

## Task 6: 中文配音 Provider、字幕和音频资产

**Files:**
- Create: `services/backend/app/integrations/tts/base.py`
- Create: `services/backend/app/integrations/tts/edge.py`
- Create: `services/backend/app/integrations/tts/disabled.py`
- Create: `services/backend/app/services/audio_generation.py`
- Create: `services/backend/app/media/subtitles.py`
- Modify: `services/backend/app/core/config.py`
- Modify: `services/backend/pyproject.toml`
- Test: `services/backend/tests/integrations/test_tts_provider.py`
- Test: `services/backend/tests/services/test_audio_generation.py`
- Test: `services/backend/tests/media/test_subtitles.py`

**Interfaces:**
- Produces: `TtsProvider.synthesize(SpeechRequest) -> AsyncIterator[bytes]`; `EdgeTtsProvider`; `DisabledTtsProvider`; `AudioGenerationService.generate(version_id)`; WebVTT/SRT builders from persisted cues。

- [ ] **Step 1: Write failing provider, disabled-state, timing and tenant-isolation tests**

验证语音文本/voice 在服务端白名单内、Provider 未配置时阻止合成、音频失败不创建假素材、字幕时间单调且不越过镜头边界、相同输入幂等复用音频素材。

- [ ] **Step 2: Run tests and verify RED**

Run: `cd services/backend && uv run pytest tests/integrations/test_tts_provider.py tests/services/test_audio_generation.py tests/media/test_subtitles.py -q`

- [ ] **Step 3: Implement provider boundary and configurable Edge TTS adapter**

默认中文旁白 voice 为可配置白名单项；Provider 网络错误映射为稳定脱敏错误码。数据库仅保存 provider 名称、voice、语言和音频素材来源，不保存任何未来 Provider Secret。

- [ ] **Step 4: Build deterministic subtitle cues and persist audio/subtitle assets**

旁白和对白基于镜头目标时长分配时间，用户可在时间线中调整；SRT/WebVTT 内容使用参数文件输入 FFmpeg，不进入命令行拼接。

- [ ] **Step 5: Verify GREEN and full backend suite**

Run: `cd services/backend && uv run pytest tests/integrations/test_tts_provider.py tests/services/test_audio_generation.py tests/media/test_subtitles.py -q && uv run pytest -q`

- [ ] **Step 6: Commit**

```bash
git add services/backend/app/integrations/tts services/backend/app/services/audio_generation.py services/backend/app/media/subtitles.py services/backend/app/core/config.py services/backend/pyproject.toml services/backend/tests
git commit -m "feat: add configurable narration and subtitles"
```

## Task 7: 简化时间线和幂等成片合成

**Files:**
- Create: `services/backend/app/services/timeline_render.py`
- Create: `services/backend/app/media/render.py`
- Modify: `services/backend/app/api/productions.py`
- Test: `services/backend/tests/services/test_timeline_render.py`
- Test: `services/backend/tests/api/test_timeline.py`
- Test: `services/backend/tests/media/test_render.py`

**Interfaces:**
- Produces: timeline clips with `shot_id, asset_id, order_index, trim_in_ms, trim_out_ms, transition, volume`; subtitle track; narration track; optional uploaded music track; `POST /versions/{id}/renders`; `GET /renders/{id}`。

- [ ] **Step 1: Write failing timeline validation and render idempotency tests**

覆盖镜头排序、裁切越界、仅允许 hard-cut/crossfade、音量范围、素材跨租户拒绝、缺失镜头/TTS 阻止导出、相同 revision 重复点击只创建一个 render。

- [ ] **Step 2: Run tests and verify RED**

Run: `cd services/backend && uv run pytest tests/services/test_timeline_render.py tests/api/test_timeline.py tests/media/test_render.py -q`

- [ ] **Step 3: Implement immutable timeline revisions and FFmpeg render graph**

每次编辑创建新 revision；渲染固定某一 revision。视频统一规格后连接，旁白/对白混音，字幕生成可切换软字幕 WebVTT 与烧录字幕，首版成片输出 H.264/AAC MP4。

- [ ] **Step 4: Probe and persist final render atomically**

ffprobe 验证可解码、分辨率、FPS、像素格式和时长后，才创建最终 Asset/Render 完成记录；失败保留脱敏诊断和可重试输入，不覆盖上一版成片。

- [ ] **Step 5: Verify GREEN**

Run: `cd services/backend && uv run pytest tests/services/test_timeline_render.py tests/api/test_timeline.py tests/media/test_render.py -q`

- [ ] **Step 6: Commit**

```bash
git add services/backend/app/services/timeline_render.py services/backend/app/media/render.py services/backend/app/api/productions.py services/backend/tests
git commit -m "feat: render versioned short story timelines"
```

## Task 8: Web 分镜编排台、关键帧审阅和时间线

**Files:**
- Create: `apps/web/app/(studio)/productions/page.tsx`
- Create: `apps/web/app/(studio)/productions/[productionId]/page.tsx`
- Create: `apps/web/components/production/StoryInput.tsx`
- Create: `apps/web/components/production/StoryboardEditor.tsx`
- Create: `apps/web/components/production/VisualBible.tsx`
- Create: `apps/web/components/production/ShotCard.tsx`
- Create: `apps/web/components/production/TimelineEditor.tsx`
- Create: `apps/web/components/production/RenderPanel.tsx`
- Create: `apps/web/lib/api/productions.ts`
- Modify: `apps/web/app/(studio)/layout.tsx`
- Test: `apps/web/tests/production-workflow.test.tsx`
- Test: `apps/web/tests/timeline-editor.test.tsx`

**Interfaces:**
- Consumes: Task 3/4/7 production APIs and existing asset access API。
- Produces: 中文三阶段工作台“故事与分镜 → 关键帧与镜头 → 配音字幕与成片”。

- [ ] **Step 1: Read the relevant Next.js 16 guides under `apps/web/node_modules/next/dist/docs/`**

记录本次使用的路由、服务端/客户端组件和数据获取约束，避免沿用旧版 Next.js API。

- [ ] **Step 2: Write failing component tests**

验证规划前后状态、六镜头编辑、批准确认、未批准按钮禁用、单镜头重试、时间线重排/裁切/转场/音量、字幕编辑、失败项定位和刷新恢复。

- [ ] **Step 3: Run tests and verify RED**

Run: `cd apps/web && npm test -- --run production-workflow.test.tsx timeline-editor.test.tsx`

- [ ] **Step 4: Implement accessible responsive production workspace**

保持现有中文视觉语言；键盘可操作镜头排序并提供非拖拽替代按钮；状态不以颜色作为唯一表达；所有异步操作保留项目/作品/版本上下文。

- [ ] **Step 5: Verify GREEN, typecheck and build**

Run: `cd apps/web && npm test -- --run && npm run typecheck && npm run build`

- [ ] **Step 6: Commit**

```bash
git add apps/web
git commit -m "feat: add short story production workspace"
```

## Task 9: 浏览器验收、真实 Provider 烟雾与文档闭环

**Files:**
- Create: `e2e/short-story.spec.ts`
- Create: `docs/acceptance/short-story-production.md`
- Modify: `README.md`
- Modify: `docs/operations.md`
- Modify: `docs/superpowers/specs/2026-10-16-ai-video-studio-design.md`

**Interfaces:**
- Produces: 可重复的本地浏览器验收；远程真实生成证据；下一阶段长文本拆解的准确接入点。

- [ ] **Step 1: Write failing Playwright journey**

使用确定性适配器覆盖创建作品、规划、编辑、批准、关键帧、镜头、配音字幕、时间线、成片、刷新恢复和审阅者只读。

- [ ] **Step 2: Run browser test and verify RED**

Run: `cd e2e && npx playwright test short-story.spec.ts`

- [ ] **Step 3: Complete browser wiring and verify GREEN**

Run: `cd e2e && npx playwright test`

- [ ] **Step 4: Run full local acceptance**

Run backend full suite, frontend tests/typecheck/build, Playwright, `docker compose config --quiet`, `docker compose up -d --build`, API/Worker/media-worker health and Alembic empty-database upgrade/check.

- [ ] **Step 5: Run controlled real-provider acceptance**

先验证 Ollama/ComfyUI/TTS 健康与 ComfyUI 队列为空；生成一个六镜头约 30 秒故事。记录脱敏 task/render IDs、各阶段耗时、工作流版本、音视频 probe 摘要、浏览器播放结果和失败/重试情况，不记录 Secret、完整私密原文或原始远程日志。

- [ ] **Step 6: Update durable docs and acceptance evidence**

README 标明已实现/未实现边界；运维文档加入 media-worker、TTS 和渲染恢复；主设计文档将阶段 5/6 标记为已交付并指向验收记录。

- [ ] **Step 7: Commit**

```bash
git add e2e README.md docs
git commit -m "docs: verify short story production pipeline"
```

## Completion Contract

- 六镜头短故事从文字规划到 MP4 成片可在 Web 完成，所有 GPU 消耗均在明确批准之后。
- 任一镜头、语音或渲染失败可定位、可恢复、可单独重试，不破坏其他合格素材。
- 作品版本、镜头、生成任务、素材、音频、字幕、时间线和 Render 可双向追溯。
- Backend、Web、Playwright、Docker、迁移、FFmpeg/ffprobe 和至少一次真实六镜头验收均有新鲜证据。
- 仓库 README、运维文档、验收文档、GitHub 分支和 Obsidian 项目总览同步。

