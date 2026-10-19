# 短故事配音字幕视频生产链 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有文字生成图片/单镜头视频闭环上，交付“短故事 → 可审阅分镜 → 六个约 5 秒镜头 → 中文配音与字幕 → 简化时间线 → MP4 成片”的 Web 生产链，并让后续小说分集流程复用同一套内容与素材模型。

**Architecture:** 保持 Next.js + FastAPI 模块化单体和 ARQ Worker 架构，在 PostgreSQL 中增加作品、版本、Character/Scene Bible、镜头、台词、对齐、字幕、口型、质检和时间线模型。Ollama 只生成版本化结构化规划；用户批准分镜和关键帧后，现有 GenerationTask/GenerationStep/Asset 流程串行消费 GPU；独立 media-worker 负责 FFmpeg/ffprobe、字幕、混音和成片合成，不占 GPU 租约。最终语音是字幕与口型的唯一时间轴权威来源，失败阶段按镜头和素材血缘局部重做。

**Tech Stack:** Next.js 16、React 19、TypeScript、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、ARQ、PostgreSQL、Redis、MinIO、Ollama、Windows 原生 ComfyUI 0.18.5、ACE-Step 1.5、Stable Audio Open 1.0、Qwen3-TTS 0.6B CustomVoice Provider、强制对齐与口型 Provider、FFmpeg/ffprobe、Pytest、Vitest、Playwright。

**Spec:** `docs/superpowers/specs/2026-10-16-ai-video-studio-design.md`

## Global Constraints

- 中文 UI、业务状态和可操作错误；代码标识和协议字段保持英文。
- 内容层级固定为 `作品 -> 版本 -> 分集 -> 场景 -> 镜头 -> 生成任务 -> 素材版本`，短故事也使用该层级，不另建一次性模型。
- 30 秒标准短片固定为 6 个约 5 秒镜头；单镜头继续使用 512×512、81 帧、16 FPS、20 steps 的已审核工作流。
- 用户批准分镜前不得提交图片或视频 GPU 任务；关键帧批准前不得提交对应镜头视频任务。
- Ollama 规划请求使用 `keep_alive: "0s"`，并保存请求模型、实际模型、回退原因、模板版本和 Schema 版本。
- 浏览器不得接触 Ollama、ComfyUI、TTS Provider 或 Cloudflare Access 凭据。
- ComfyUI 生产入口固定为 `https://comfyui.lsgood.cn`，通过 Cloudflare Access 连接 Windows 原生 `127.0.0.1:8190`；不得改回 WSL 8188。
- 音乐、音效、TTS、口型与图片/视频共享全局串行 GPU 租约；ComfyUI 提交前 queue 必须为空，任务前后调用 `/free`，不得自动并发重试。
- 语音能力通过 Qwen3-TTS Provider 接入；Provider 传输契约未配置时必须显示“未配置”并阻止合成，不得把 Windows CLI 当作远程 API 或生成空白音轨冒充配音。
- Task 6 开始前必须取得并版本化服务端 Qwen3-TTS、强制对齐和口型 Provider 的认证、提交、状态、取消和下载契约；不得猜测端点或绕过 Access。
- 最终音频是字幕和口型的权威时间轴；先生成语音和词级对齐，再生成字幕和口型，字幕误差目标不超过 120ms。
- Character Bible 与 Scene Bible、角色/场景主参考、实际 seed/模型/LoRA/IP-Adapter/FaceID 参数均版本化并随镜头追溯。
- 口型/对齐模型、允许误差、一致性阈值、转场策略和局部重试次数使用租户级后台生产策略，不硬编码。
- 每个镜头和 Render 必须区分 `generated_keyframe_motion` 与 `full_generated_video`，关键图运动化不得标成完整生成式视频。
- `lip_sync_verified` 默认 false；只有官方 InfiniteTalk 完整模型栈在 RTX 3060 12GB 上真实通过后才能置 true，镜头规避可见嘴部不等于口型已验证。
- 合成案例必须保留虚构声明；Z-Image INT8 `int8_tensorwise` 已知不兼容工作流不得作为自动回退。
- media-worker 不持有 GPU 租约；所有媒体输入先从平台对象存储下载，输出校验后再写回平台对象存储。
- 合成前统一分辨率、FPS、SAR、色彩空间和 `yuv420p`；成片必须通过 ffprobe 可解码性与时长校验。
- 多租户、项目成员权限、幂等、配额预留、取消、恢复和敏感信息过滤继续沿用首个切片规则。
- 不实现任意多轨、复杂关键帧动画、数字人、自动批量生成整部小说或未经审阅的持续 GPU 消耗。

## Review Focus

- Ollama 返回缺字段、重复镜头 ID、总时长超限或无法解析 JSON：规划任务应进入可修订失败状态，不创建半成品镜头，也不消耗 GPU。
- 两个浏览器标签同时批准同一分镜/关键帧或修改已批准版本：只产生一组任务；修改必须创建保留来源的新版本。
- 多人镜头 speaker 锁定错误、静音持续张嘴、字幕超出 120ms 或未验证口型被标成 true：阻止成片，只重做对应镜头口型/对齐层，不重做已通过语音。
- queue 非空、`/free` 失败或 Access 401/403：不得继续提交或自动并发重试，401/403 固定显示“服务认证失败”。
- 人物/场景漂移或转场出现闪黑帧、主体变形、节奏停顿、对白截断：Gate 定位到具体 shot/transition，只进入局部重试。

---

## File Structure

```text
services/backend/app/
├── domain/production/        # 作品层级、视觉圣经、镜头、台词、时间线、成片
├── api/productions.py        # 作品、版本、规划、批准、镜头与时间线 API
├── services/story_planning.py
├── services/shot_generation.py
├── services/timeline_render.py
├── integrations/audio/       # ComfyUI 音乐/音效、Qwen TTS、对齐和口型 Provider
├── services/continuity.py    # 人物、场景与转场质量检查
└── media/                     # FFmpeg 命令构建、探测、字幕、混音与 QC
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
- Modify: `services/backend/app/domain/generation/models.py`
- Modify: `services/backend/app/domain/generation/repository.py`
- Test: `services/backend/tests/domain/test_production_hierarchy.py`
- Test: `services/backend/tests/domain/test_production_versioning.py`

**Interfaces:**
- Consumes: `Tenant`, `Project`, `User`, `GenerationTask`, `Asset`。
- Produces: `Production`, `ProductionVersion`, `Episode`, `Scene`, `Shot`, `CharacterCard`, `CharacterReferenceVersion`, `SceneBible`, `SceneReferenceVersion`, `StyleBible`, `DialogueLine`, `WordAlignment`, `SubtitleCue`, `ShotQualityCheck`, `Timeline`, `TimelineClip`, `TimelineTransition`, `Render`; `MediaGenerationMode = generated_keyframe_motion|full_generated_video`; `GenerationStep.checkpoint_data/qa_status`; `ProductionRepository.create_version(...)`; `approve_storyboard(...)`; `revise_from(version_id) -> ProductionVersion`。

- [ ] **Step 1: Write failing hierarchy and versioning tests**

覆盖租户/项目外键、短故事默认单集、场景与镜头稳定排序、六镜头总时长约 30 秒、批准后的内容不可原地改写、修订创建新版本并保留来源版本；角色/场景主参考可版本化和锁定，刷新读取保持同一上下文。验证镜头/时间线/Render 保存 `media_generation_mode`，关键图运动镜头必须有 `source_image_id` 和 shot/cue 映射；`lip_sync_verified` 默认 false；GenerationStep 恢复点与 QA 状态可独立更新。

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd services/backend && uv run pytest tests/domain/test_production_hierarchy.py tests/domain/test_production_versioning.py -q`

Expected: FAIL because `app.domain.production` and migration `0009` do not exist.

- [ ] **Step 3: Implement models, schemas, repository transactions and migration**

镜头保存 `order_index`、目标时长、景别、机位、动作、动作起止、视线/屏幕运动方向、视觉提示词、`transition_reason`、旁白/对白引用、批准状态、`media_generation_mode`、`source_image_id`、关键帧/原视频/口型视频当前素材 ID、`lip_sync_status` 和 `lip_sync_verified=false`。`DialogueLine`、`WordAlignment` 与 `SubtitleCue` 共同保存 `dialogue_id`、`speaker_id`、`shot_id`、`audio_asset_id`、`subtitle_cue_id`、`start_ms/end_ms` 和词级时间戳；角色/场景参考保存主资产、实际 seed、模型/LoRA/IP-Adapter/FaceID 参数版本。GenerationStep 新增 JSON 恢复点和 `qa_status=pending|passed|failed|not_applicable|passed_with_limitations`，长文本步骤固定为 `source_preprocessed|production_design_locked|keyframes_generated|narration_generated|alignment_completed|timeline_built|subtitles_built|audio_mixed|render_packaged|qa_completed`。版本状态使用 `draft|planned|storyboard_approved|keyframes_approved|render_ready|completed`。

- [ ] **Step 4: Apply migration and verify GREEN**

Run: `cd services/backend && uv run alembic upgrade head && uv run pytest tests/domain/test_production_hierarchy.py tests/domain/test_production_versioning.py -q`

Expected: PASS and `uv run alembic check` reports no new operations.

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/domain/production services/backend/app/domain/generation services/backend/alembic/versions/0009_short_story_production.py services/backend/tests/domain
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

验证未批准分镜不能生成关键帧、未批准关键帧不能生成视频、六镜头任务严格串行、单镜头失败可独立重试、Worker 重启复用已有 prompt_id/素材/恢复点且不重复提交；续镜继承上一镜已通过的角色/场景参考和末帧，实际 seed/模型/适配器参数快照可追溯。Z-Image INT8 出现 `int8_tensorwise` 时必须明确失败或使用管理员配置的 Wan 2.2 工作流，不得静默自动回退。

- [ ] **Step 2: Run tests and verify RED**

Run: `cd services/backend && uv run pytest tests/services/test_shot_generation.py tests/worker/test_story_recovery.py tests/api/test_shot_generation.py -q`

- [ ] **Step 3: Implement shot-to-generation linkage and batch orchestration**

关键帧与镜头视频仍是普通 GenerationTask/GenerationStep/Asset；Shot 只保存当前选择、来源引用和生产策略快照。队列按镜头顺序提交，但 GPU 租约仍是全局并发 1；连续动作把上一镜末帧作为下一镜视觉条件，跨场景变化必须带 `transition_reason`。限定 PID 的 Windows 服务恢复后重新核验 win32、8190、队列和模型清单，再从恢复点继续，已完成素材不得重新生成。

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
- Create: `services/backend/app/services/continuity.py`
- Create: `services/backend/app/worker/media_runtime.py`
- Create: `services/backend/app/worker/media_settings.py`
- Modify: `services/backend/Dockerfile`
- Modify: `docker-compose.yml`
- Test: `services/backend/tests/media/test_probe.py`
- Test: `services/backend/tests/media/test_frame_sampling.py`
- Test: `services/backend/tests/services/test_continuity.py`
- Test: `services/backend/tests/worker/test_media_jobs.py`

**Interfaces:**
- Produces: `probe_video(path) -> VideoProbe`; `sample_review_frames(path, policy) -> list[FrameSample]`; `ContinuityEvaluator.evaluate(shot_id, frame_samples, audio_probe, policy) -> ShotQualityCheck`; `normalize_clip(input, output, profile)`; ARQ queue `media` with stable job IDs。

- [ ] **Step 1: Write failing probe, sampling and idempotent media-job tests**

使用小型仓库内生成夹具，验证首/中/末帧、错误帧率/像素格式拒绝、损坏 MP4 拒绝、重复 media job 不产生多个 Render；人物脸型/发色/服装/年龄观感、场景光线/道具/轴线、运动方向和环境音连续性低于后台阈值时只标记对应镜头失败。

- [ ] **Step 2: Run tests and verify RED**

Run: `cd services/backend && uv run pytest tests/media tests/services/test_continuity.py tests/worker/test_media_jobs.py -q`

- [ ] **Step 3: Install FFmpeg and implement argument-list based subprocess wrappers**

禁止 `shell=True`；文件名、字幕和用户文本不得拼接为 shell 命令。标准输出为 512×512、16 FPS、SAR 1:1、BT.709、`yuv420p`、H.264/AAC MP4。

- [ ] **Step 4: Add independent media-worker service and verify it never acquires GpuLease**

Run: `docker compose config --quiet && cd services/backend && uv run pytest tests/media tests/services/test_continuity.py tests/worker/test_media_jobs.py -q`

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/media services/backend/app/worker/media_runtime.py services/backend/app/worker/media_settings.py services/backend/Dockerfile docker-compose.yml services/backend/tests
git commit -m "feat: add media quality and processing worker"
```

## Task 6: 音乐、音效、Qwen3-TTS、强制对齐和口型资产

**Files:**
- Create: `services/backend/app/integrations/audio/base.py`
- Create: `services/backend/app/integrations/audio/qwen_tts.py`
- Create: `services/backend/app/integrations/audio/alignment.py`
- Create: `services/backend/app/integrations/audio/lip_sync.py`
- Create: `services/backend/app/integrations/audio/disabled.py`
- Create: `services/backend/app/services/audio_generation.py`
- Create: `services/backend/app/media/subtitles.py`
- Create: `services/backend/app/workflows/templates/ace_step_1_5_v1.json`
- Create: `services/backend/app/workflows/templates/stable_audio_open_v1.json`
- Create: `services/backend/alembic/versions/0010_production_policies.py`
- Modify: `services/backend/app/integrations/comfyui.py`
- Modify: `services/backend/app/workflows/registry.py`
- Modify: `services/backend/app/workflows/policies.py`
- Modify: `services/backend/app/domain/ai_resources/models.py`
- Modify: `services/backend/app/domain/ai_resources/schemas.py`
- Modify: `services/backend/app/domain/ai_resources/repository.py`
- Modify: `services/backend/app/api/admin_ai_resources.py`
- Modify: `services/backend/app/domain/generation/models.py`
- Modify: `services/backend/app/domain/generation/schemas.py`
- Modify: `services/backend/app/domain/generation/repository.py`
- Modify: `services/backend/app/api/productions.py`
- Modify: `services/backend/app/core/config.py`
- Test: `services/backend/tests/integrations/test_audio_providers.py`
- Test: `services/backend/tests/integrations/test_comfyui_audio_contract.py`
- Test: `services/backend/tests/services/test_audio_generation.py`
- Test: `services/backend/tests/services/test_lip_sync.py`
- Test: `services/backend/tests/media/test_subtitles.py`
- Test: `services/backend/tests/api/test_production_policies.py`
- Test: `services/backend/tests/domain/test_audio_task_metadata.py`
- Test: `services/backend/tests/api/test_shot_stage_retry.py`

**Interfaces:**
- Consumes: Task 1 `DialogueLine`/`WordAlignment`/`SubtitleCue`/`ShotQualityCheck`; server-delivered versioned Qwen3-TTS transport contract（must exist before this task; do not guess an endpoint）。
- Produces: `SpeechProvider.synthesize(SpeechRequest) -> SpeechResult`; `AlignmentProvider.align(audio_asset_id, transcript) -> AlignmentResult`; `LipSyncProvider.apply(LipSyncRequest) -> LipSyncResult`; `AudioGenerationService.generate(version_id)`; `ProductionPolicy`; `ComfyUIAdapter.prepare_exclusive_generation()`/`release_models()`; SRT/ASS builders; `POST /shots/{id}/steps/{step}/retry`; `GET /versions/{id}/production-status`。

- [ ] **Step 1: Write failing audio contract, provider, timing, queue and tenant-isolation tests**

验证：ACE 工作流固定同时包含 0.6B/1.7B 编码器；Stable Audio 只开放白名单参数；提交前 queue 为空并调用 `/free`，结束/失败后再次 `/free`；queue 非空不提交且不自动并发重试；401/403 映射“服务认证失败”。验证 Qwen TTS Provider 未配置时阻止合成、音频失败不创建假素材、相同输入幂等复用音频；最终音频产生词级时间戳，字幕逐字匹配、单调、不跨镜头且起止误差不超过 120ms；多人镜头未锁定 speaker 时禁止口型任务，静音人物不得持续张嘴。未经 InfiniteTalk 12GB 真实验收时 `lip_sync_verified` 始终为 false；规避可见嘴部的镜头使用 `not_required_by_shot_design`，不能伪造已验证状态。

- [ ] **Step 2: Run tests and verify RED**

Run: `cd services/backend && uv run pytest tests/integrations/test_audio_providers.py tests/integrations/test_comfyui_audio_contract.py tests/services/test_audio_generation.py tests/services/test_lip_sync.py tests/media/test_subtitles.py tests/api/test_production_policies.py tests/domain/test_audio_task_metadata.py tests/api/test_shot_stage_retry.py -q`

- [ ] **Step 3: Implement exclusive ComfyUI audio workflows and configurable production policy**

从交接工作流复制审核后的节点结构并清除业务示例提示词；`WorkflowRegistry` 只注入时长、seed、采样、tags/lyrics 或正负提示词等白名单字段。实现 queue 空闲检查、任务前后 `/free` 和稳定错误码。新增租户级 `ProductionPolicy`，保存口型模型、对齐模型、允许误差、人物/场景阈值、转场白名单/时长和局部重试次数；每个任务保存策略版本快照。扩展 `GenerationKind` 为 `music|sound_effect|speech|alignment|lip_sync`，任务持久化 capability、脱敏 `parameter_summary`、`remote_submitted_at`、`finished_at`、`prompt_id` 和脱敏失败原因，输出继续作为 Asset 关联。

- [ ] **Step 4: Implement Qwen3-TTS, alignment, subtitles, lip sync and lineage**

Qwen3-TTS 只通过已交付的服务端受控契约调用，默认 voice/instruction 由后台白名单管理，Provider Secret 不写数据库。先持久化最终语音 Asset，再按实际语音时长（不是文本长度估算）强制对齐并保存句/词级时间戳，随后生成底部安全区白字暗色描边/底板的 SRT/ASS 和口型派生视频；原视频、口型版、对齐结果、字幕和最终输出建立父子素材关系。口型失败只把该镜头的 `lip_sync` GenerationStep 标记为可重做，不重新生成已通过语音或原视频。

- [ ] **Step 5: Verify GREEN and full backend suite**

Run: `cd services/backend && uv run pytest tests/integrations/test_audio_providers.py tests/integrations/test_comfyui_audio_contract.py tests/services/test_audio_generation.py tests/services/test_lip_sync.py tests/media/test_subtitles.py tests/api/test_production_policies.py tests/domain/test_audio_task_metadata.py tests/api/test_shot_stage_retry.py -q && uv run pytest -q`

- [ ] **Step 6: Commit**

```bash
git add services/backend/app/integrations/audio services/backend/app/integrations/comfyui.py services/backend/app/services/audio_generation.py services/backend/app/media/subtitles.py services/backend/app/workflows services/backend/app/domain/ai_resources services/backend/app/domain/generation services/backend/app/api/admin_ai_resources.py services/backend/app/api/productions.py services/backend/app/core/config.py services/backend/alembic/versions/0010_production_policies.py services/backend/tests
git commit -m "feat: add traceable audio alignment and lip sync"
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
- Produces: timeline clips with `shot_id, asset_id, order_index, trim_in_ms, trim_out_ms, volume`; `TimelineTransition(transition_type, duration_ms, outgoing_handle_ms, incoming_handle_ms, audio_bridge)`; aligned subtitle track; narration/dialogue, ACE music and Stable Audio ambience tracks; `POST /versions/{id}/renders`; `GET /renders/{id}`。

- [ ] **Step 1: Write failing timeline validation and render idempotency tests**

覆盖镜头排序、裁切越界、转场类型/时长不在租户策略白名单时拒绝、句柄区间越界、音量范围、素材跨租户拒绝、缺失镜头/TTS/对齐/连续性 Gate 阻止导出；只有 `visible_speech_required=true` 的镜头缺失已验证口型时阻止导出，`not_required_by_shot_design` 可带明确限制完成。相同 revision 重复点击只创建一个 render。验证动作连续镜头优先 hard-cut/match-cut，配乐和环境音跨镜头连续，旁白时自动 ducking，对白切点不截断呼吸和尾音。

- [ ] **Step 2: Run tests and verify RED**

Run: `cd services/backend && uv run pytest tests/services/test_timeline_render.py tests/api/test_timeline.py tests/media/test_render.py -q`

- [ ] **Step 3: Implement immutable timeline revisions and FFmpeg render graph**

每次编辑创建新 revision；渲染固定某一 revision。视频统一规格后连接；根据镜头元数据选择动作/视线/构图匹配、J/L cut、短交叉淡化或硬切，不对所有镜头机械套同一转场。旁白/对白、连续配乐和环境音完成自动 ducking，字幕使用对齐后的 SRT/ASS；首版成片输出 H.264/AAC MP4。

- [ ] **Step 4: Probe and persist final render atomically**

逐转场检查首尾帧运动向量、主体位置、曝光、色温以及闪帧/黑帧/主体变形/节奏停顿；音频 Gate 验证 LUFS、True Peak、采样率、声道和全片解码，不只判断文件存在。通过后再由 ffprobe 和完整解码验证可解码、分辨率、FPS、像素格式和时长，最后创建 Asset/Render 完成记录。失败保存具体 transition/shot Gate、脱敏诊断和可重试输入，不覆盖上一版成片。

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
- Create: `apps/web/components/production/ShotStageStatus.tsx`
- Create: `apps/web/components/production/ProductionPolicyPanel.tsx`
- Create: `apps/web/components/production/RenderPanel.tsx`
- Create: `apps/web/lib/api/productions.ts`
- Modify: `apps/web/app/(studio)/layout.tsx`
- Test: `apps/web/tests/production-workflow.test.tsx`
- Test: `apps/web/tests/timeline-editor.test.tsx`

**Interfaces:**
- Consumes: Task 3/4/6/7 production, stage-retry and policy APIs plus existing asset access API。
- Produces: 中文三阶段工作台“故事与分镜 → 关键帧与镜头 → 配音/对齐/口型/质检 → 字幕时间线与成片”；租户管理员生产策略页面。

- [ ] **Step 1: Read the relevant Next.js 16 guides under `apps/web/node_modules/next/dist/docs/`**

记录本次使用的路由、服务端/客户端组件和数据获取约束，避免沿用旧版 Next.js API。

- [ ] **Step 2: Write failing component tests**

验证规划前后状态、六镜头编辑、批准确认、未批准按钮禁用、时间线重排/裁切/转场/音量、字幕编辑和刷新恢复。每张镜头卡必须显示 `source_image_id`、shot/cue 关系、恢复点、语音、字幕、口型、角色一致性、环境一致性、转场和人工复核状态；失败操作只提交对应 `shot_id + step` 的局部重做。界面分别标记“关键图运动成片”与“完整生成式视频”，并独立显示“真实口型已验证/未验证/镜头设计无需口型”。角色/场景主参考刷新后保持选中；Access 错误显示“服务认证失败”；Provider 未配置时按钮禁用并显示“未配置”。

- [ ] **Step 3: Run tests and verify RED**

Run: `cd apps/web && npm test -- --run production-workflow.test.tsx timeline-editor.test.tsx`

- [ ] **Step 4: Implement accessible responsive production workspace**

保持现有中文视觉语言；键盘可操作镜头排序并提供非拖拽替代按钮；状态不以颜色作为唯一表达；所有异步操作保留项目/作品/版本/镜头/失败阶段上下文。后台参数页可配置口型/对齐模型、允许误差、角色/场景阈值、转场类型/时长和局部重试次数，但只显示服务端允许值，不接受任意模型名或工作流。

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
- Create: `docs/acceptance/case-0001-long-form.md`
- Modify: `README.md`
- Modify: `docs/operations.md`
- Modify: `docs/superpowers/specs/2026-10-16-ai-video-studio-design.md`

**Interfaces:**
- Produces: 可重复的本地浏览器验收；远程真实生成证据；下一阶段长文本拆解的准确接入点。

- [ ] **Step 1: Write failing Playwright journey**

使用确定性适配器覆盖创建作品、规划、编辑、批准、关键帧、镜头、最终语音、词级对齐、字幕、speaker 锁定、口型、人物/环境连续性质检、逐阶段局部重做、转场、混音、成片、刷新恢复和审阅者只读。断言关键图运动作品不能显示为完整生成视频，`lip_sync_verified` 默认 false，恢复后不重复生成已完成素材，合成案例页面显示虚构声明。

- [ ] **Step 2: Run browser test and verify RED**

Run: `cd e2e && npx playwright test short-story.spec.ts`

- [ ] **Step 3: Complete browser wiring and verify GREEN**

Run: `cd e2e && npx playwright test`

- [ ] **Step 4: Run full local acceptance**

Run backend full suite, frontend tests/typecheck/build, Playwright, `docker compose config --quiet`, `docker compose up -d --build`, API/Worker/media-worker health and Alembic empty-database upgrade/check.

- [ ] **Step 5: Run controlled real-provider acceptance**

先验证 Ollama、Windows 原生 ComfyUI、Qwen3-TTS/对齐/口型 Provider 健康与 ComfyUI 队列为空；确认任务前后 `/free` 且无并发重试。生成一个六镜头约 30 秒故事，并执行最终 Gate：逐句试听和口型检查、字幕与语音误差不超过 120ms、逐镜头首中末帧人物/环境一致性、逐转场播放、LUFS/True Peak/采样率/声道、ffprobe 与完整解码。记录脱敏 task/render IDs、各阶段耗时、工作流/模型/策略版本、质检分数、音视频 probe 摘要、浏览器播放结果和局部重试情况，不记录 Secret、完整私密原文或原始远程日志。

CASE-0001 作为已验证参考回归：24 段旁白、24 条字幕、15 张有效图中 13 张进入 24 片段时间线，输出 245.440 秒 H.264 1280×720 16fps + AAC 48kHz 双声道，-15.9 LUFS、True Peak -1.5 dBFS，全片解码通过。验收记录必须标明 `media_generation_mode=generated_keyframe_motion`、`lip_sync_verified=false` 和 `status=passed_with_documented_limitations`，不得把它计为完整生成视频或真实 InfiniteTalk 口型通过。

- [ ] **Step 6: Update durable docs and acceptance evidence**

README 标明已实现/未实现边界；运维文档加入 media-worker、TTS 和渲染恢复；主设计文档将阶段 5/6 标记为已交付并指向验收记录。

- [ ] **Step 7: Commit**

```bash
git add e2e README.md docs
git commit -m "docs: verify short story production pipeline"
```

## Completion Contract

- 六镜头短故事从文字规划到 MP4 成片可在 Web 完成，所有 GPU 消耗均在明确批准之后。
- 每个镜头和 Render 明确区分 `generated_keyframe_motion` 与 `full_generated_video`，并保留 `source_image_id`、shot/cue、Bible、恢复点和 QA 血缘。
- 最终语音、词级时间戳、字幕和口型使用同一权威时间轴；字幕起止误差目标不超过 120ms，speaker 锁定正确，静音人物不持续张嘴。
- `lip_sync_verified` 默认 false；镜头设计规避可见嘴部可以记录限制并成片，但不得宣称真实口型同步。
- 任一镜头的语音、字幕、口型、人物一致性、环境一致性、转场或渲染失败可定位、可恢复、可只重做失败阶段，不破坏其他合格素材。
- 作品版本、镜头、生成任务/步骤、角色/场景参考、原视频、口型版、音频、对齐、SRT/ASS、质检、时间线和 Render 可双向追溯。
- 每个 ComfyUI 音频任务严格执行 queue 空闲 → `/free` → 单任务 → history/download → `/free`；401/403 显示“服务认证失败”。
- 逐句试听/口型、逐镜头首中末帧、人物/环境连续性、逐转场播放、响度/True Peak/采样率/声道、ffprobe 和完整解码全部通过。
- Backend、Web、Playwright、Docker、迁移、FFmpeg/ffprobe 和至少一次真实六镜头验收均有新鲜证据。
- 仓库 README、运维文档、验收文档、GitHub 分支和 Obsidian 项目总览同步。

