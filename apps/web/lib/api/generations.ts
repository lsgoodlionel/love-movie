import { api } from "./client";

export type GenerationKind = "image" | "video";
export type GenerationAccepted = { task_id: string; status: string };

export type GenerationInput = {
  project_id: string;
  prompt: string;
  seed: number;
  width?: number;
  height?: number;
  camera_pose?: string;
  camera_speed?: number;
};

export function createGeneration(kind: GenerationKind, input: GenerationInput, idempotencyKey: string) {
  return api<GenerationAccepted>(`/v1/generations/${kind === "image" ? "images" : "videos"}`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(input),
  });
}
