"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Building2, LockKeyhole, Mail, User } from "lucide-react";
import { authUrl } from "@/components/AuthGate";
import { startCheckout } from "@/lib/billing";

export default function RegisterPage() {
  const router = useRouter();
  const firstField = useRef<HTMLInputElement>(null);
  const [requestedPlan, setRequestedPlan] = useState("FREE");
  const premiumRequest = requestedPlan === "START" || requestedPlan === "TOP";
  const [companyName, setCompanyName] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    firstField.current?.focus();
    const plan = new URLSearchParams(window.location.search).get("plan")?.toUpperCase();
    if (plan === "START" || plan === "TOP" || plan === "FREE") setRequestedPlan(plan);
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault(); setError("");
    if (password !== confirmPassword) return setError("Le password non coincidono");
    if (password.length < 12) return setError("La password deve contenere almeno 12 caratteri");
    if (!accepted) return setError("Devi accettare termini e condizioni");
    setBusy(true);
    try {
      const response = await fetch(authUrl("/auth/register"), { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ company_name: companyName, name, email, password }) });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Registrazione non disponibile");
      if (requestedPlan === "START" || requestedPlan === "TOP") {
        try {
          const { checkout_url } = await startCheckout(requestedPlan);
          window.location.assign(checkout_url);
        } catch {
          router.replace("/dashboard?checkout=error");
        }
        return;
      }
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registrazione non disponibile");
    } finally { setBusy(false); }
  }

  return <section className="auth-page"><div className="auth-orb" /><div className="auth-card auth-card-register"><div className="auth-card-head"><span className="panel-number">CREA ACCOUNT</span><h1>Inizia con Net Billy.</h1><p>Il tuo workspace viene creato con il piano Free.</p>{premiumRequest && <div className="plan-notice" role="status">Hai selezionato <b>{requestedPlan}</b>. Dopo la registrazione verrai indirizzato al Checkout sicuro Stripe.</div>}</div><form onSubmit={submit} className="auth-form"><label htmlFor="register-company">Attività / Ragione sociale<span className="auth-input"><Building2 size={17} /><input ref={firstField} id="register-company" autoComplete="organization" required value={companyName} onChange={e => setCompanyName(e.target.value)} /></span></label><label htmlFor="register-name">Nome<span className="auth-input"><User size={17} /><input id="register-name" autoComplete="name" required value={name} onChange={e => setName(e.target.value)} /></span></label><label htmlFor="register-email">Email<span className="auth-input"><Mail size={17} /><input id="register-email" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></span></label><label htmlFor="register-password">Password<span className="auth-input"><LockKeyhole size={17} /><input id="register-password" type="password" autoComplete="new-password" minLength={12} required value={password} onChange={e => setPassword(e.target.value)} /></span><small>Almeno 12 caratteri.</small></label><label htmlFor="register-confirm">Conferma password<span className="auth-input"><LockKeyhole size={17} /><input id="register-confirm" type="password" autoComplete="new-password" minLength={12} required value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} /></span></label><label className="terms"><input type="checkbox" checked={accepted} onChange={e => setAccepted(e.target.checked)} required /> <span>Accetto termini e condizioni.</span></label>{error && <div className="alert error" role="alert">{error}</div>}<button className="button primary full" disabled={busy}>{busy ? (premiumRequest ? "Apertura Checkout…" : "Registrazione in corso…") : <>{premiumRequest ? `Continua con ${requestedPlan}` : "Crea account Free"} <ArrowRight size={17} /></>}</button></form><p className="auth-switch">Hai già un account? <Link href="/login">Accedi</Link></p></div></section>;
}
