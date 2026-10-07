"use client";
import { useEffect, useRef } from "react";
import { connectionRequest, readConnection } from "../lib/connection";
import "../public/cte-archive.css";

export default function CteArchive() {
  const target = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    const path = "/cte-archive.js";
    import(/* webpackIgnore: true */ path).then(module => {
      if (cancelled || !target.current) return;
      return module.mountArchive(target.current, { connection: readConnection, request: async () => {
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
