"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowUpRight, LogIn, LogOut, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { authUrl, SessionUser } from "./AuthGate";

export default function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<SessionUser | null>(null);
  const isPublic = pathname.replace(/\/+$/, "") === "";

  useEffect(() => {
    fetch(authUrl("/auth/me"), { credentials: "include" })
      .then(response => response.ok ? response.json() : null)
      .then(setUser).catch(() => setUser(null));
  }, []);

  async function signOut() {
    await fetch(authUrl("/auth/logout"), { method: "POST", credentials: "include" });
    router.replace("/");
  }

  return <header className="header"><div className="shell header-inner">
    <Link href={isPublic ? "/" : "/dashboard"} className="brand" aria-label="Net Billy, homepage"><span className="brand-icon"><Zap size={25} fill="currentColor" /></span><span><strong>NET BILLY<span className="brand-dot">.</span></strong><small>ENERGY WORKSPACE</small></span></Link>
    {isPublic ? <nav aria-label="Navigazione principale"><a href="#come-funziona">Come funziona</a><a href="#vantaggi">Vantaggi</a><a href="#prezzi">Prezzi</a></nav> : <nav aria-label="Navigazione principale"><Link href="/dashboard" aria-current={pathname === "/dashboard" ? "page" : undefined}>Panoramica</Link><Link href="/cte" aria-current={pathname === "/cte" ? "page" : undefined}>Carica CTE</Link><Link href="/bollette" aria-current={pathname === "/bollette" ? "page" : undefined}>Confronta bollette</Link></nav>}
    <div className="header-actions">{isPublic ? (user ? <Link className="button primary header-cta" href="/dashboard">Vai alla dashboard <ArrowUpRight size={16} /></Link> : <><Link className="header-login" href="/login">Accedi <LogIn size={15} /></Link><Link className="button primary header-cta" href="/register">Inizia gratis <ArrowUpRight size={16} /></Link></>) : <>{user && <span className="tiny-label">{user.name || user.tenant.name} · {user.plan.code || "PIANO"}</span>}<button className="button outline header-cta" onClick={() => void signOut()}>Esci <LogOut size={16} /></button></>}</div>
  </div></header>;
}
