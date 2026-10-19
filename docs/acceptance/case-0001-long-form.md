# CASE-0001 长文本成片参考验收

- 验证日期：2026-10-19
- 状态：`passed_with_documented_limitations`
- 证据目录：`/Users/lionel/Develop/comfyui-output/case-0001-4min`
- 最终成片：`case-0001-final.mp4`

## 已验证结果

- 时长：245.440 秒。
- 视频：H.264，1280×720，16fps。
- 音频：AAC，48kHz，双声道。
- 综合响度：-15.9 LUFS；True Peak：-1.5 dBFS。
- 全片解码：通过。
- 内容结构：24 段隔离 Qwen3-TTS 中文旁白、24 条字幕、24 个时间线片段。
- 画面：15 张有效 Wan 2.2 关键图，其中 13 张进入时间线。
- 声音：ACE-Step 无歌词音乐与 Stable Audio 室内环境音；旁白优先，音乐和环境音下压。
- 人工抽检：5、48、94、140、188、238 秒，未观察到黑帧、字幕截断或明显画面破损。

## 生产流程

1. 保存原始长文并压缩为 24 段旁白，保留虚构声明、四组事实条件、即时结果和关系比较。
2. 固化 Character Bible、Scene Bible、镜头语言、字幕和音频方向，并形成 24 个视觉提示。
3. Windows 原生 ComfyUI 8190 使用已验证 Wan 2.2 14B 四步工作流串行生成关键图。
4. Windows 隔离 Qwen3-TTS 0.6B CustomVoice 运行时生成 24 段旁白；ComfyUI 主环境 Transformers 保持不变。
5. 按真实旁白时长构建时间线和 24 条字幕，不使用文本长度估算字幕时间。
6. 13 张关键图通过缓慢推拉、平移和裁切形成 24 个运动镜头。
7. 字幕烧录到底部安全区，使用白字和暗色描边/底板。
8. 完成配乐、环境音、旁白混音、规格封装、ffprobe、响度测量和全片解码。

## 能力边界

- `media_generation_mode=generated_keyframe_motion`。这是关键图运动化成片，不是 24 段 `full_generated_video`。
- `lip_sync_verified=false`。本次没有执行真实口型驱动，也不将规避可见嘴部算作口型通过。
- 引述对白使用旁白，并通过反应、侧面、越肩、文件、手部和细节镜头规避明显错口型。
- 只有官方 InfiniteTalk 完整模型栈在 RTX 3060 12GB 上完成真实稳定性和音画同步验收后，才允许把具体资产设为 `lip_sync_verified=true`。

## 恢复、安全与已知问题

- 每个镜头应保存 `source_image_id`、shot/cue 映射、Character/Scene Bible 版本、`prompt_id`、输出资产、恢复点和 QA 状态。
- 已完成关键图在 Worker 或 ComfyUI 恢复后不得重复生成。
- Z-Image INT8 的 `int8_tensorwise` 兼容错误已复现；不得自动回退到该已知不兼容工作流。
- LoRA 模型补丁缓存异常只能通过限定 PID 的 Windows 原生 ComfyUI 重启恢复；重启后重新确认 `os=win32`、8190、队列为空和模型清单，禁止误切回 WSL 8188。
- 合成案例必须显示虚构声明，不得包装成真实机构事件。
- 日志、API、数据库和前端不得记录 Cloudflare Access 凭据、SSH 私钥或完整敏感配置。

## 原始证据

- `validation-report.md`
- `test-results.json`
- `production-design.md`
- `timeline.json`
- `subtitles.srt`
- `build_image_requests.py`
- `run_images.py`
- `build_final.py`

原始证据保留在交接目录，不整体复制进产品仓库；仓库只保存无凭据验收摘要和实现边界。
