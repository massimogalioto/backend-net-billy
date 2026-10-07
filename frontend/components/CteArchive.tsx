"use client";
import { useEffect, useRef } from "react";
import { connectionRequest, readConnection, directConnection } from "../lib/connection";
import "../public/cte-archive.css";

export default function CteArchive() {
  const target = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    const path = "/cte-archive.js";
    import(/* webpackIgnore: true */ path).then(module => {
      if (cancelled || !target.current) return;
      return module.mountArchive(target.current, { connection: readConnection, update: async (id: string, changes: Record<string, unknown>) => {
        const settings = readConnection();
        const headers = new Headers({ "Content-Type": "application/json" });
        if (directConnection && settings.key) headers.set("x-api-key", settings.key);
        const url = directConnection ? `${settings.url.replace(/\/+$/, "")}/cte-offers/${encodeURIComponent(id)}` : `/api/cte-offers/${encodeURIComponent(id)}`;
        const response = await fetch(url, { method: "PATCH", headers, body: JSON.stringify(changes), signal: AbortSignal.timeout(30_000) });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Dati CTE non validi");
      }, request: async () => {
        const response = await fetch(...connectionRequest("/api/service/cte-offers", { signal: AbortSignal.timeout(30_000) }));
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Archivio CTE non disponibile");
        return data;
      } });
    }).catch(() => { if (!cancelled && target.current) target.current.textContent = "Archivio CTE non disponibile"; });
    return () => { cancelled = true; };
  }, []);
  return <div ref={target} className="panel" aria-label="Archivio CTE attive" />;
}
