"use client";

import { useEffect, useState } from "react";

import { accessAsset, Asset, listAssets } from "../../../lib/api/assets";

export default function AssetsPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [urls, setUrls] = useState<Record<string, string>>({});
  useEffect(() => { void listAssets().then(setAssets); }, []);
  async function preview(asset: Asset) {
    const result = await accessAsset(asset.id);
    setUrls((current) => ({ ...current, [asset.id]: result.url }));
  }
  return (
    <main className="studio-main">
      <section className="studio-intro"><div><p className="eyebrow">ASSET LIBRARY</p><h1>团队素材库</h1></div><p>所有生成结果按项目和任务保留来源关系，访问链接按需签发。</p></section>
      <div className="asset-grid">
        {assets.map((asset) => <article className="asset-card" key={asset.id}>
          <div className="asset-canvas">
            {urls[asset.id] ? (asset.kind === "video" ? <video src={urls[asset.id]} controls /> : <img src={urls[asset.id]} alt="生成素材" />) : <button onClick={() => preview(asset)}>点击预览</button>}
          </div>
          <div><strong>{asset.kind === "video" ? "视频镜头" : "图片素材"}</strong><small>{(asset.size_bytes / 1024 / 1024).toFixed(2)} MB</small></div>
        </article>)}
        {!assets.length && <p className="empty-row">素材库还是空的，先去快速生成台创作。</p>}
      </div>
    </main>
  );
}
