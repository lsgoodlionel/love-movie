"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "../../lib/api/client";
import { createGeneration, GenerationKind } from "../../lib/api/generations";

type Project = { id: string; name: string };

export function GenerationForm({
  projects,
  onAccepted,
  pending: forcedPending,
  fieldError: forcedError,
  onCreateProject,
}: {
  projects: Project[];
  onAccepted: (taskId: string, projectId: string, kind: GenerationKind) => void;
  pending?: boolean;
  fieldError?: string;
  onCreateProject?: () => void;
}) {
  const [kind, setKind] = useState<GenerationKind>("image");
  const [prompt, setPrompt] = useState("");
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [seed, setSeed] = useState(0);
  const [cameraPose, setCameraPose] = useState("Zoom In");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const retryIdentity = useRef<{ fingerprint: string; key: string } | null>(null);
  const pending = forcedPending ?? submitting;

  useEffect(() => {
    if (!projectId && projects[0]) setProjectId(projects[0].id);
  }, [projectId, projects]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending || !projectId || !prompt.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const input = {
        project_id: projectId,
        prompt: prompt.trim(),
        seed,
        ...(kind === "image"
          ? { width: 768, height: 1024 }
          : { camera_pose: cameraPose, camera_speed: 0.45 }),
      };
      const fingerprint = JSON.stringify({ kind, ...input });
      if (retryIdentity.current?.fingerprint !== fingerprint) {
        retryIdentity.current = { fingerprint, key: crypto.randomUUID() };
      }
      const accepted = await createGeneration(kind, input, retryIdentity.current.key);
      retryIdentity.current = null;
      onAccepted(accepted.task_id, projectId, kind);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "提交失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="generation-form" onSubmit={submit}>
      <div className="mode-switch" aria-label="生成类型">
        <button type="button" className={kind === "image" ? "active" : ""} onClick={() => setKind("image")}>
          生成图片
        </button>
        <button type="button" className={kind === "video" ? "active" : ""} onClick={() => setKind("video")}>
          生成视频
        </button>
      </div>

      <label>
        <span>项目</span>
        <select value={projectId} onChange={(event) => setProjectId(event.target.value)} required>
          <option value="">选择一个项目</option>
          {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
      </label>

      <label>
        <span>描述你想生成的画面</span>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder={kind === "image" ? "例如：雨夜的上海弄堂，暖色窗光，电影胶片质感" : "例如：清晨山谷云雾流动，镜头缓慢向前推进"}
          rows={8}
          maxLength={4000}
          required
        />
        <small>{prompt.length} / 4000</small>
      </label>

      <div className="field-grid">
        <label>
          <span>随机种子</span>
          <input type="number" min="0" value={seed} onChange={(event) => setSeed(Number(event.target.value))} />
        </label>
        {kind === "image" ? (
          <label><span>画幅</span><select disabled><option>3:4 · 768×1024</option></select></label>
        ) : (
          <label>
            <span>镜头运动</span>
            <select value={cameraPose} onChange={(event) => setCameraPose(event.target.value)}>
              <option value="Zoom In">缓慢推进</option>
              <option value="Zoom Out">缓慢拉远</option>
              <option value="Pan Left">向左横移</option>
              <option value="Pan Right">向右横移</option>
              <option value="Static">固定镜头</option>
            </select>
          </label>
        )}
      </div>

      {(forcedError || error) && <p className="field-error" role="alert">{forcedError || error}</p>}
      {!projects.length && <div className="project-empty"><p className="field-note">还没有项目，请先创建一个创作空间。</p>{onCreateProject && <button type="button" className="secondary-action" onClick={onCreateProject}>新建“第一个项目”</button>}</div>}
      <button className="primary-action" type="submit" disabled={pending || !projects.length}>
        {pending ? "正在提交…" : `开始生成${kind === "image" ? "图片" : "视频"}`}
      </button>
    </form>
  );
}
