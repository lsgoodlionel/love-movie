import { api } from "./client";

export type Task = {
  id: string;
  project_id: string;
  kind: "image" | "video";
  status: string;
  current_step: string | null;
  error_code: string | null;
};

export function getTask(id: string) {
  return api<Task>(`/v1/tasks/${id}`);
}

export function cancelTask(id: string) {
  return api<{ status: string }>(`/v1/tasks/${id}/cancel`, { method: "POST" });
}
