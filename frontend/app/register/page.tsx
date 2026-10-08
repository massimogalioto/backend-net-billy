"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { authUrl } from "@/components/AuthGate";

export default function RegisterPage() {
  const router = useRouter();
  const [companyName, setCompanyName] = useState(""); const [name, setName] = useState("");
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState(""); const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError("");
    if (password !== confirmPassword) { setError("Le password non coincidono"); return; }
    if (password.length < 12) { setError("La password deve contenere almeno 12 caratteri"); return; }
    if (!accepted) { setError("Devi accettare termini e condizioni"); return; }
    setBusy(true);
    try {
      const response = await fetch(authUrl("/auth/register"), { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ company_name: companyName, name, email, password }) });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Registrazione non disponibile");
      router.replace("/");
    } catch (err) { setError(err instanceof Error ? err.message : "Registrazione non disponibile"); } finally { setBusy(false); }
  }
  return <main className="shell workspace"><section className="panel" style={{ maxWidth: 560, margin: "6vh auto" }}><span className="panel-number">NET BILLY</span><h1>Crea il tuo spazio.</h1><p className="muted">Inizia con il piano Free.</p><form onSubmit={submit} className="offerta-fields"><label>Nome attività / Ragione sociale<input autoComplete="organization" required value={companyName} onChange={e => setCompanyName(e.target.value)} /></label><label>Nome<input autoComplete="name" required value={name} onChange={e => setName(e.target.value)} /></label><label>Email<input type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></label><label>Password<input type="password" autoComplete="new-password" minLength={12} required value={password} onChange={e => setPassword(e.target.value)} /><small>Almeno 12 caratteri.</small></label><label>Conferma password<input type="password" autoComplete="new-password" minLength={12} required value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} /></label><label style={{ display: "flex", gap: 8, alignItems: "center" }}><input type="checkbox" checked={accepted} onChange={e => setAccepted(e.target.checked)} required /> Accetto termini e condizioni</label>{error && <div className="alert error" role="alert">{error}</div>}<button className="button primary full" disabled={busy}>{busy ? "Registrazione in corso…" : "Crea account"}</button></form><p className="form-note">Hai già un account? <Link href="/login">Accedi</Link></p></section></main>;
}
