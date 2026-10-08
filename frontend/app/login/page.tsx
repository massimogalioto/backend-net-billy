"use client";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authUrl } from "@/components/AuthGate";

export default function LoginPage() {
  const router = useRouter(); const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { fetch(authUrl("/auth/me"), { credentials: "include" }).then(r => { if (r.ok) router.replace("/"); }); }, [router]);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try {
    const response = await fetch(authUrl("/auth/login"), { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
    if (!response.ok) throw new Error("Email o password non validi"); router.replace("/");
  } catch (err) { setError(err instanceof Error ? err.message : "Accesso non disponibile"); } finally { setBusy(false); } }
  return <main className="shell workspace"><section className="panel" style={{ maxWidth: 480, margin: "8vh auto" }}><span className="panel-number">NET BILLY</span><h1>Accedi al tuo spazio.</h1><p className="muted">Gestisci CTE e confronti del tuo tenant.</p><form onSubmit={submit} className="offerta-fields"><label>Email<input type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></label><label>Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>{error && <div className="alert error" role="alert">{error}</div>}<button className="button primary full" disabled={busy}>{busy ? "Accesso in corso…" : "Accedi"}</button></form><p className="form-note">Non hai un account? <Link href="/register">Registrati</Link></p></section></main>;
}
