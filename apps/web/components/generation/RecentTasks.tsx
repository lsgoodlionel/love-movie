import { translateTaskStatus } from "./TaskProgress";

export type RecentTask = { id: string; projectId: string; kind: "image" | "video"; status: string; prompt: string };

export function RecentTasks({ tasks, onSelect }: { tasks: RecentTask[]; onSelect: (task: RecentTask) => void }) {
  return (
    <section className="recent-section">
      <div className="section-heading"><div><p className="eyebrow">RECENT RUNS</p><h2>最近任务</h2></div><span>{tasks.length} 个</span></div>
      {tasks.length ? (
        <div className="recent-grid">
          {tasks.map((task) => (
            <button key={task.id} className="recent-card" onClick={() => onSelect(task)}>
              <span className={`kind-icon ${task.kind}`}>{task.kind === "image" ? "图" : "影"}</span>
              <strong>{task.prompt}</strong>
              <small>{translateTaskStatus(task.status)}</small>
            </button>
          ))}
        </div>
      ) : <p className="empty-row">还没有生成记录，先完成你的第一帧。</p>}
    </section>
  );
}
