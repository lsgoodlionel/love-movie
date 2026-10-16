import { expect, test } from "@playwright/test";

test("刷新后工作台仍可恢复并继续使用", async ({ page }) => {
  await page.route("**/api/v1/projects", (route) => route.fulfill({ json: [{ id: "project-1", name: "长篇项目" }] }));
  await page.route("**/api/v1/tasks", (route) => route.fulfill({ json: [{ id: "task-history", project_id: "project-1", kind: "image", status: "running", current_step: null, error_code: null }] }));
  await page.route("**/api/v1/tasks/task-history", (route) => route.fulfill({ json: { id: "task-history", project_id: "project-1", kind: "image", status: "running", current_step: null, error_code: null } }));
  await page.route("**/api/v1/tasks/task-history/events", (route) => route.fulfill({ contentType: "text/event-stream", body: "" }));
  await page.goto("/generate");
  await expect(page.getByRole("option", { name: "长篇项目" })).toBeAttached();
  await page.reload();
  await expect(page.getByRole("option", { name: "长篇项目" })).toBeAttached();
  await expect(page.getByRole("heading", { name: "生成结果" })).toBeVisible();
  await expect(page.getByText("正在生成").first()).toBeVisible();
});
