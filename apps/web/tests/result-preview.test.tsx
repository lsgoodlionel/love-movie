import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ResultPreview } from "../components/generation/ResultPreview";

describe("ResultPreview", () => {
  it("renders image and video previews", () => {
    const image = renderToStaticMarkup(
      <ResultPreview asset={{ id: "a", kind: "image", url: "/image.png" }} />,
    );
    const video = renderToStaticMarkup(
      <ResultPreview asset={{ id: "v", kind: "video", url: "/video.mp4" }} />,
    );
    expect(image).toContain("<img");
    expect(video).toContain("<video");
    expect(video).toContain("controls");
    expect(video).toContain("下载素材");
  });
});
