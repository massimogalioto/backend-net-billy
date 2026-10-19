"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, LockKeyhole, Mail } from "lucide-react";
import { authUrl } from "@/components/AuthGate";

export default function LoginPage() {
  const router = useRouter(); const emailRef = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { emailRef.current?.focus(); fetch(authUrl("/auth/me"), { credentials: "include" }).then(r => { if (r.ok) router.replace("/dashboard"); }); }, [router]);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { const response = await fetch(authUrl("/auth/login"), { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) }); if (!response.ok) throw new Error("Email o password non validi"); router.replace("/dashboard"); } catch (err) { setError(err instanceof Error ? err.message : "Accesso non disponibile"); } finally { setBusy(false); } }
  return <section className="auth-page"><div className="auth-orb" /><div className="auth-card"><div className="auth-card-head"><span className="panel-number">BENTORNATO</span><h1>Accedi al tuo workspace.</h1><p>Gestisci CTE e confronti in modo ordinato.</p></div><form onSubmit={submit} className="auth-form"><label htmlFor="login-email">Email<span className="auth-input"><Mail size={17} /><input ref={emailRef} id="login-email" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></span></label><label htmlFor="login-password">Password<span className="auth-input"><LockKeyhole size={17} /><input id="login-password" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></span></label>{error && <div className="alert error" role="alert">{error}</div>}<button className="button primary full" disabled={busy}>{busy ? "Accesso in corso…" : <>Accedi <ArrowRight size={17} /></>}</button></form><p className="auth-switch">Non hai un account? <Link href="/register?plan=FREE">Inizia gratuitamente</Link></p></div></section>;
}
