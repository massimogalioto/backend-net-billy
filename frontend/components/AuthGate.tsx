"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { directConnection, readConnection } from "@/lib/connection";

export type SessionUser = { name: string; email: string; tenant: { name: string }; plan: { code?: string; name?: string } };
export function authUrl(path: string) { return directConnection ? `${readConnection().url}${path}` : path; }

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname(); const router = useRouter(); const [ready, setReady] = useState(pathname === "/login");
  useEffect(() => {
    if (pathname === "/login") { setReady(true); return; }
    fetch(authUrl("/auth/me"), { credentials: "include" }).then(response => {
      if (!response.ok) router.replace("/login"); else setReady(true);
    }).catch(() => router.replace("/login"));
  }, [pathname, router]);
  if (!ready) return <main className="shell workspace"><p className="muted">Verifica sessione in corso…</p></main>;
  return <>{children}</>;
}
