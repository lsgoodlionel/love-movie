"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "../../../lib/api/client";
import { login } from "../../../lib/api/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await login(email, password);
      router.replace("/generate");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "登录失败，请稍后重试");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-brand">
        <p className="eyebrow">LOVE MOVIE · AI PRODUCTION</p>
        <h1>把故事，变成<br />看得见的世界。</h1>
        <p>从一句灵感到图片、镜头与长篇动画素材，保留每一次创作脉络。</p>
      </section>
      <form className="login-card" onSubmit={submit}>
        <p className="eyebrow">团队工作台</p>
        <h2>欢迎回来</h2>
        <label><span>邮箱</span><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label><span>密码</span><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {error && <p className="field-error">{error}</p>}
        <button className="primary-action" disabled={pending}>{pending ? "正在登录…" : "进入创作台"}</button>
        <small>当前为内部团队私有平台</small>
      </form>
    </main>
  );
}
