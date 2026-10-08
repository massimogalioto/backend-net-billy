"use client";

import { useEffect, useState } from "react";
import { authUrl } from "./AuthGate";

type Usage = {
  plan: { code: string; name: string };
  cte: { used: number; limit: number; remaining: number };
  comparisons: { used: number; limit: number; remaining: number; period: string };
};

function nearLimit(used: number, limit: number) {
  return limit > 0 && used / limit >= 0.8;
}

export function UsageSummary() {
  const [usage, setUsage] = useState<Usage | null>(null);
  useEffect(() => {
    fetch(authUrl("/account/usage"), { credentials: "include" })
      .then((response) => response.ok ? response.json() : null)
      .then(setUsage)
      .catch(() => setUsage(null));
  }, []);
  if (!usage) return null;
  const cteWarning = nearLimit(usage.cte.used, usage.cte.limit);
  const comparisonWarning = nearLimit(usage.comparisons.used, usage.comparisons.limit);
  return <section className="shell usage-summary" aria-label="Utilizzo del piano">
    <div className="usage-panel">
      <div><span className="tiny-label">PIANO ATTIVO</span><strong>{usage.plan.code}</strong><small>{usage.plan.name}</small></div>
      <div className={cteWarning ? "usage-meter warning" : "usage-meter"}><span>CTE attive</span><strong>{usage.cte.used} / {usage.cte.limit}</strong>{cteWarning && <small>Limite quasi raggiunto</small>}</div>
      <div className={comparisonWarning ? "usage-meter warning" : "usage-meter"}><span>Confronti questo mese</span><strong>{usage.comparisons.used} / {usage.comparisons.limit}</strong>{comparisonWarning && <small>Limite quasi raggiunto</small>}</div>
    </div>
  </section>;
}
