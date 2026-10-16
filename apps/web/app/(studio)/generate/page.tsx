"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { GenerationForm } from "../../../components/generation/GenerationForm";
import { RecentTask, RecentTasks } from "../../../components/generation/RecentTasks";
import { PreviewAsset, ResultPreview } from "../../../components/generation/ResultPreview";
import { TaskProgress } from "../../../components/generation/TaskProgress";
import { ApiError, api } from "../../../lib/api/client";
import { accessAsset, listAssets } from "../../../lib/api/assets";
import { GenerationKind } from "../../../lib/api/generations";
import { Task } from "../../../lib/api/tasks";

type Project = { id: string; name: string };

export default function GeneratePage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState("");
  const [preview, setPreview] = useState<PreviewAsset | null>(null);
  const [recent, setRecent] = useState<RecentTask[]>([]);

  useEffect(() => {
    api<Project[]>("/v1/projects").then(setProjects).catch((error) => {
      if (error instanceof ApiError && error.status === 401) router.replace("/login");
      else setProjects([]);
    });
  }, [router]);

  const taskChanged = useCallback(async (task: Task) => {
    setRecent((items) => items.map((item) => item.id === task.id ? { ...item, status: task.status } : item));
    if (task.status !== "completed") return;
    const assets = await listAssets(task.project_id);
    const result = assets.find((asset) => asset.generation_task_id === task.id && asset.kind === task.kind)
      ?? assets.find((asset) => asset.generation_task_id === task.id);
    if (!result) return;
    const access = await accessAsset(result.id);
    setPreview({ id: result.id, kind: result.kind, url: access.url });
  }, []);

  return (
    <main className="studio-main">
      <section className="studio-intro">
        <div><p className="eyebrow">QUICK CREATE</p><h1>从一个念头，<em>生成第一帧。</em></h1></div>
        <p>输入中文描述，生成可追踪、可预览、可继续剪辑的图片与单镜头视频素材。</p>
      </section>
      <section className="creation-grid">
        <div className="panel form-panel">
          <div className="panel-number">01</div>
          <GenerationForm projects={projects} onCreateProject={async () => {
            const created = await api<Project>("/v1/projects", { method: "POST", body: JSON.stringify({ name: "第一个项目" }) });
            setProjects([created]);
          }} onAccepted={(id, selectedProject, kind: GenerationKind) => {
            setTaskId(id);
            setProjectId(selectedProject);
            setPreview(null);
            setRecent((items) => [{ id, kind, status: "queued", prompt: kind === "image" ? "新图片任务" : "新视频任务" }, ...items]);
          }} />
        </div>
        <div className="panel preview-panel">
          <div className="panel-number">02</div>
          <div className="panel-title"><div><p className="eyebrow">LIVE RESULT</p><h2>生成结果</h2></div><span className="privacy-badge">仅团队可见</span></div>
          <ResultPreview asset={preview} />
          <TaskProgress taskId={taskId} onChange={taskChanged} />
          {projectId && <small className="trace-id">项目追踪：{projectId.slice(0, 8)}</small>}
        </div>
      </section>
      <RecentTasks tasks={recent} onSelect={setTaskId} />
    </main>
  );
}
