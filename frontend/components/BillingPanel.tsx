"use client";

import { ArrowUpRight, CreditCard, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AccountUsage,
  ApiError,
  authenticatedJson,
  BillingStatus,
  openCustomerPortal,
  startCheckout,
} from "@/lib/billing";

const ACTIVE_STRIPE_STATUSES = new Set(["active", "trialing"]);

function formatDate(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat("it-IT", { dateStyle: "long" }).format(date);
}

function statusLabel(status: string | null) {
  if (!status) return "Piano gratuito";
  return ({ active: "Attivo", trialing: "Periodo di prova", past_due: "Pagamento in ritardo", unpaid: "Pagamento non riuscito", paused: "In pausa", canceled: "Annullato" } as Record<string, string>)[status] ?? status;
}

export function BillingPanel() {
  const router = useRouter();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"START" | "TOP" | "portal" | null>(null);
  const [error, setError] = useState("");
  const [checkoutResult, setCheckoutResult] = useState<"success" | "cancelled" | "error" | null>(null);
  const [syncing, setSyncing] = useState(false);
  const attempts = useRef(0);

  const handleError = useCallback((reason: unknown) => {
    if (reason instanceof ApiError && reason.status === 401) {
      router.replace("/login");
      return;
    }
    setError(reason instanceof Error ? reason.message : "Il servizio non è disponibile. Riprova tra poco.");
  }, [router]);

  const refresh = useCallback(async (verifyUsage = false) => {
    setError("");
    try {
      const requests: [Promise<BillingStatus>, Promise<AccountUsage>?] = [
        authenticatedJson<BillingStatus>("/billing/status"),
      ];
      if (verifyUsage) requests.push(authenticatedJson<AccountUsage>("/account/usage"));
      const [nextStatus] = await Promise.all(requests);
      setStatus(nextStatus);
      if (verifyUsage) window.dispatchEvent(new Event("net-billy:usage-refresh"));
      return nextStatus;
    } catch (reason) {
      handleError(reason);
      return null;
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  useEffect(() => {
    const checkout = new URLSearchParams(window.location.search).get("checkout");
    const result = checkout === "success" || checkout === "cancelled" || checkout === "error" ? checkout : null;
    setCheckoutResult(result);
    setSyncing(result === "success");
    void refresh(result === "success");
  }, [refresh]);

  useEffect(() => {
    if (!syncing || !status) return;
    if (ACTIVE_STRIPE_STATUSES.has(status.stripe_status ?? "") && status.plan_code !== "FREE") {
      setSyncing(false);
      return;
    }
    if (attempts.current >= 4) { setSyncing(false); return; }
    const timer = window.setTimeout(async () => {
      attempts.current += 1;
      await refresh(true);
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [refresh, status, syncing]);

  async function checkout(plan: "START" | "TOP") {
    setBusy(plan); setError("");
    try {
      const { checkout_url } = await startCheckout(plan);
      window.location.assign(checkout_url);
    } catch (reason) {
      handleError(reason); setBusy(null);
    }
  }

  async function portal() {
    setBusy("portal"); setError("");
    try {
      const { portal_url } = await openCustomerPortal();
      window.location.assign(portal_url);
    } catch (reason) {
      handleError(reason); setBusy(null);
    }
  }

  const hasStripeSubscription = Boolean(status?.stripe_status);
  const synchronized = Boolean(status && ACTIVE_STRIPE_STATUSES.has(status.stripe_status ?? "") && status.plan_code !== "FREE");
  return <section className="shell billing-section" aria-labelledby="billing-title">
    {checkoutResult === "success" && <div className="alert success" role="status"><RefreshCw className={syncing ? "spin" : ""} size={18} /><span><strong>{syncing ? "Pagamento ricevuto, sincronizzazione in corso…" : synchronized ? "Abbonamento sincronizzato." : "Pagamento ricevuto. La sincronizzazione richiede ancora qualche istante."}</strong><small>{syncing ? "Stiamo verificando piano e utilizzo. L’attivazione dipende dalla conferma Stripe." : synchronized ? "Il nuovo piano e i relativi limiti sono ora disponibili." : "Ricarica la pagina tra poco: l’accesso verrà aggiornato solo dopo la conferma Stripe."}</small></span></div>}
    {checkoutResult === "cancelled" && <div className="alert" role="status">Checkout annullato. Il tuo piano non è stato modificato.</div>}
    {checkoutResult === "error" && <div className="alert error" role="alert">Account creato, ma non è stato possibile aprire Checkout. Puoi riprovare dal pannello abbonamento.</div>}
    <div className="billing-panel">
      <div className="billing-heading"><div><span className="panel-number">ABBONAMENTO</span><h2 id="billing-title">Il tuo piano NET BILLY</h2><p>Controlla lo stato oppure gestisci il pagamento sul portale sicuro Stripe.</p></div><span className="billing-icon"><CreditCard size={25} /></span></div>
      {loading && <p className="muted">Caricamento abbonamento…</p>}
      {error && <div className="alert error" role="alert">{error}<button className="text-button" onClick={() => void refresh(true)}>Riprova</button></div>}
      {status && <>
        <div className="billing-details">
          <div><span>Piano</span><strong>{status.plan_code}</strong><small>{status.plan_name}</small></div>
          <div><span>Stato</span><strong>{statusLabel(status.stripe_status)}</strong><small>{status.plan_status}</small></div>
          <div><span>Prossima scadenza</span><strong>{formatDate(status.current_period_end)}</strong><small>{status.cancel_at_period_end ? "Nessun rinnovo automatico" : hasStripeSubscription ? "Rinnovo automatico" : "Nessuna scadenza"}</small></div>
        </div>
        {status.cancel_at_period_end && <div className="billing-cancellation" role="status">L’abbonamento è stato annullato, ma rimarrà attivo fino al {formatDate(status.current_period_end)}. Dopo tale data il piano tornerà FREE.</div>}
        <div className="billing-actions">
          {!hasStripeSubscription && status.plan_code === "FREE" && <>
            <button className="button primary" disabled={busy !== null} onClick={() => void checkout("START")}>{busy === "START" ? "Apertura Checkout…" : "Acquista START — €14,99/mese + IVA"} <ArrowUpRight size={16} /></button>
            <button className="button outline" disabled={busy !== null} onClick={() => void checkout("TOP")}>{busy === "TOP" ? "Apertura Checkout…" : "Acquista TOP — €45/mese + IVA"} <ArrowUpRight size={16} /></button>
          </>}
          {hasStripeSubscription && <button className="button primary" disabled={busy !== null} onClick={() => void portal()}>{busy === "portal" ? "Apertura portale…" : "Gestisci abbonamento"} <ArrowUpRight size={16} /></button>}
        </div>
      </>}
    </div>
  </section>;
}
