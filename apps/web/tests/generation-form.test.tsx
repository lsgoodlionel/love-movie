import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { GenerationForm } from "../components/generation/GenerationForm";

describe("GenerationForm", () => {
  it("renders Chinese image and video controls", () => {
    const html = renderToStaticMarkup(
      <GenerationForm projects={[{ id: "p-1", name: "测试项目" }]} onAccepted={() => undefined} />,
    );
    expect(html).toContain("描述你想生成的画面");
    expect(html).toContain("生成图片");
    expect(html).toContain("生成视频");
    expect(html).toContain("开始生成");
  });

  it("disables duplicate submit while pending and displays field error", () => {
    const html = renderToStaticMarkup(
      <GenerationForm projects={[]} onAccepted={() => undefined} pending fieldError="图片宽度超出限制" />,
    );
    expect(html).toContain("正在提交");
    expect(html).toContain("disabled");
    expect(html).toContain("图片宽度超出限制");
  });
});
