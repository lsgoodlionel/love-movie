import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TaskProgress, translateTaskStatus } from "../components/generation/TaskProgress";

describe("TaskProgress", () => {
  it("translates task states to Chinese", () => {
    expect(translateTaskStatus("queued")).toBe("等待生成");
    expect(translateTaskStatus("completed")).toBe("生成完成");
  });

  it("shows reconnect state without leaking raw failures", () => {
    const html = renderToStaticMarkup(<TaskProgress taskId="task-1" reconnecting />);
    expect(html).toContain("正在重新连接");
    expect(html).not.toContain("REMOTE_HTML");
  });
});
