"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowUpRight, LogOut, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authUrl, SessionUser } from "./AuthGate";

export default function Header() {
  const pathname = usePathname();
  const router = useRouter(); const [user, setUser] = useState<SessionUser | null>(null);
  useEffect(() => { fetch(authUrl("/auth/me"), { credentials: "include" }).then(r => r.ok ? r.json() : null).then(setUser).catch(() => setUser(null)); }, []);
  async function signOut() { await fetch(authUrl("/auth/logout"), { method: "POST", credentials: "include" }); router.replace("/login"); }
  return <header className="header"><div className="shell header-inner">
    <Link href="/" className="brand" aria-label="Energia Workspace, homepage"><span className="brand-icon"><Zap size={25} fill="currentColor" /></span><span><strong>ENERGIA<span className="brand-dot">.</span></strong><small>WORKSPACE</small></span></Link>
    <nav aria-label="Navigazione principale">
      <Link href="/" aria-current={pathname === "/" ? "page" : undefined}>Panoramica</Link>
      <Link href="/cte" aria-current={pathname === "/cte" ? "page" : undefined}>Carica CTE</Link>
      <Link href="/bollette" aria-current={pathname === "/bollette" ? "page" : undefined}>Confronta bollette</Link>
    </nav>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>{user && <span className="tiny-label">{user.name || user.tenant.name} · {user.plan.code || "PIANO"}</span>}<button className="button outline header-cta" onClick={() => void signOut()}>Esci <LogOut size={16} /></button></div>
  </div></header>;
}
