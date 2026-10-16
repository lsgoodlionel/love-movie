import Link from "next/link";
import type { ReactNode } from "react";

export default function StudioLayout({ children }: { children: ReactNode }) {
  return (
    <div className="app-frame">
      <header className="topbar">
        <Link href="/generate" className="brand"><span className="brand-mark">爱</span><span>爱视频<small>LOVE MOVIE</small></span></Link>
        <nav><Link href="/generate">快速生成</Link><Link href="/assets">素材库</Link><span className="nav-muted">故事工坊 · 即将开放</span></nav>
        <div className="account-chip"><span>内</span><div>内部团队<small>安全工作区</small></div></div>
      </header>
      {children}
    </div>
  );
}
