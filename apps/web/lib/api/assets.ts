import { api } from "./client";

export type Asset = {
  id: string;
  project_id: string;
  generation_task_id: string;
  parent_asset_id: string | null;
  kind: "image" | "video";
  content_type: string;
  size_bytes: number;
};

export function listAssets(projectId?: string) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return api<Asset[]>(`/v1/assets${query}`);
}

export function accessAsset(id: string) {
  return api<{ url: string; expires_in: number }>(`/v1/assets/${id}/access`, { method: "POST" });
}
