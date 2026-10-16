import { expect, Page, test } from "@playwright/test";

async function mockStudio(page: Page) {
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ json: { id: "project-1", name: "第一个项目" } });
    } else {
      await route.fulfill({ json: [{ id: "project-1", name: "广告片" }] });
    }
  });
  await page.route("**/api/v1/generations/**", (route) => route.fulfill({ status: 202, json: { task_id: "task-1", status: "queued" } }));
  await page.route("**/api/v1/tasks/task-1", (route) => route.fulfill({ json: { id: "task-1", project_id: "project-1", kind: "image", status: "completed", current_step: null, error_code: null } }));
  await page.route("**/api/v1/tasks/task-1/events", (route) => route.fulfill({ contentType: "text/event-stream", body: "id: 1\nevent: completed\ndata: {\"message\":\"生成完成\",\"progress\":100}\n\n" }));
  await page.route("**/api/v1/assets?**", (route) => route.fulfill({ json: [{ id: "asset-1", project_id: "project-1", generation_task_id: "task-1", parent_asset_id: null, kind: "image", content_type: "image/png", size_bytes: 100 }] }));
  await page.route("**/api/v1/assets/asset-1/access", (route) => route.fulfill({ json: { url: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='32' height='32'%3E%3Crect width='32' height='32' fill='%23ffb1c8'/%3E%3C/svg%3E", expires_in: 300 } }));
}

test("输入中文并生成可预览图片", async ({ page }) => {
  await mockStudio(page);
  await page.goto("/generate");
  await page.getByLabel("描述你想生成的画面").fill("雨夜霓虹街道，电影胶片质感");
  await page.getByRole("button", { name: "开始生成图片" }).click();
  await expect(page.getByText("生成完成").first()).toBeVisible();
  await expect(page.getByAltText("AI 生成结果")).toBeVisible();
  await expect(page.getByRole("link", { name: "下载素材" })).toBeVisible();
});

test("切换到视频保持已验证的单镜头参数入口", async ({ page }) => {
  await mockStudio(page);
  await page.goto("/generate");
  await page.getByRole("button", { name: "生成视频" }).click();
  await expect(page.getByText("镜头运动")).toBeVisible();
  await expect(page.getByRole("option", { name: "缓慢推进" })).toBeAttached();
});
