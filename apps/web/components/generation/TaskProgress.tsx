"use client";

import { useEffect, useState } from "react";

import { getTask, Task } from "../../lib/api/tasks";

const STATUS_LABELS: Record<string, string> = {
  draft: "准备中",
  validating: "正在检查参数",
  queued: "等待生成",
  planning: "正在理解创意",
  remote_submitted: "已提交生成",
  running: "正在生成",
  downloading: "正在保存结果",
  quality_check: "正在检查素材",
  persisted: "正在归档",
  completed: "生成完成",
  cancelling: "正在取消",
  cancelled: "已取消",
  failed: "生成失败",
  needs_attention: "需要处理",
};

export function translateTaskStatus(status: string) {
  return STATUS_LABELS[status] ?? "状态更新中";
}

export function TaskProgress({
  taskId,
  reconnecting: forcedReconnecting,
  onChange,
}: {
  taskId: string | null;
  reconnecting?: boolean;
  onChange?: (task: Task) => void;
}) {
  const [task, setTask] = useState<Task | null>(null);
  const [message, setMessage] = useState("等待任务");
  const [progress, setProgress] = useState(0);
  const [reconnecting, setReconnecting] = useState(false);

  useEffect(() => {
    if (!taskId) return;
    let active = true;
    let source: EventSource | null = null;

    getTask(taskId).then((current) => {
      if (!active) return;
      setTask(current);
      setMessage(translateTaskStatus(current.status));
      onChange?.(current);
      source = new EventSource(`/api/v1/tasks/${taskId}/events`, { withCredentials: true });
      source.onopen = () => setReconnecting(false);
      source.onerror = () => setReconnecting(true);
      for (const kind of Object.keys(STATUS_LABELS)) {
        source.addEventListener(kind, (event) => {
          const detail = JSON.parse((event as MessageEvent).data) as { message?: string; progress?: number };
          setMessage(detail.message || translateTaskStatus(kind));
          setProgress((current) => detail.progress ?? current);
          void getTask(taskId).then((next) => {
            setTask(next);
            onChange?.(next);
          });
        });
      }
    }).catch(() => setMessage("暂时无法读取任务状态"));

    return () => {
      active = false;
      source?.close();
    };
  }, [taskId, onChange]);

  const isReconnecting = forcedReconnecting ?? reconnecting;
  return (
    <div className="task-progress" aria-live="polite">
      <div className="progress-heading">
        <div><span className="live-dot" /><strong>{task ? translateTaskStatus(task.status) : "尚未开始"}</strong></div>
        <span>{progress}%</span>
      </div>
      <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
      <p>{isReconnecting ? "正在重新连接…" : message}</p>
      {task?.error_code && <p className="field-error">生成没有完成，请重试或联系管理员并提供任务编号。</p>}
    </div>
  );
}
