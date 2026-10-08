"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { directConnection, readConnection } from "@/lib/connection";

export type SessionUser = { name: string; email: string; tenant: { name: string }; plan: { code?: string; name?: string } };
export function authUrl(path: string) { return directConnection ? `${readConnection().url}${path}` : path; }

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname(); const router = useRouter();
  // Static export uses trailingSlash, so the browser path is /login/ on Netlify.
  const normalizedPath = pathname.replace(/\/+$/, "");
  const isPublicAuthPage = normalizedPath === "/login" || normalizedPath === "/register";
  const [ready, setReady] = useState(isPublicAuthPage);
  useEffect(() => {
    if (isPublicAuthPage) { setReady(true); return; }
    fetch(authUrl("/auth/me"), { credentials: "include" }).then(response => {
      if (!response.ok) router.replace("/login"); else setReady(true);
    }).catch(() => router.replace("/login"));
  }, [isPublicAuthPage, router]);
  if (!ready) return <main className="shell workspace"><p className="muted">Verifica sessione in corso…</p></main>;
  return <>{children}</>;
}
