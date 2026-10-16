import { api } from "./client";

export type CurrentUser = { user_id: string; tenant_id: string; email: string; role: string };

export function login(email: string, password: string) {
  return api<CurrentUser>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function me() {
  return api<CurrentUser>("/v1/auth/me");
}

export function logout() {
  return api<void>("/v1/auth/logout", { method: "POST" });
}
