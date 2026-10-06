"use client";
import { useEffect, useState } from "react";
import { connectionRequest } from "../lib/connection";

type MonthPrice = { mese: string; value_eur_smc: number | null; disp: number | null; totale: number | null };
type Prices = { previous: MonthPrice; current: MonthPrice };
const price = (value: number) => new Intl.NumberFormat("it-IT", { minimumFractionDigits: 3, maximumFractionDigits: 8 }).format(value);
const monthLabel = (month: string) => new Intl.DateTimeFormat("it-IT", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${month}-01T00:00:00Z`));

async function request(init?: RequestInit) {
  const response = await fetch(...connectionRequest("/api/service/market-prices-psv", init ?? {}));
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Prezzi PSV non disponibili");
  return data;
}

export default function MarketPrices() {
  const [prices, setPrices] = useState<Prices | null>(null);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [value, setValue] = useState("");
  const [disp, setDisp] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  function selectMonth(data: Prices, month: string) {
    const row = month === data.previous.mese ? data.previous : data.current;
    setSelectedMonth(row.mese);
    setValue(row.value_eur_smc?.toString() ?? "");
    setDisp(row.disp?.toString() ?? "");
  }
  async function load(month = selectedMonth) {
    const data: Prices = await request();
    setPrices(data);
    selectMonth(data, month);
  }
  useEffect(() => { load().catch(error => setMessage(error.message)); }, []);
  return <section className="panel" aria-labelledby="market-prices-title" style={{ marginTop: 24 }}>
    <h2 id="market-prices-title">Prezzi mercato</h2>
    <p className="muted">PSV mensile e CCR per il confronto gas. Se il mese corrente manca, usiamo il mese precedente.</p>
    {prices && <>
      <div className="stat-grid">{[prices.previous, prices.current].map(row => <div key={row.mese}>
        <span>PSV {monthLabel(row.mese)}</span>
        {row.value_eur_smc === null ? <p>Non disponibile</p> : <>
          <strong>{price(row.value_eur_smc)} <small>€/Smc</small></strong>
          <p>CCR/disp: {price(row.disp ?? 0)} €/Smc<br />Totale: {price(row.totale!)} €/Smc</p>
        </>}
      </div>)}</div>
      <form onSubmit={async event => {
        event.preventDefault(); if (busy) return;
        setBusy(true); setMessage("");
        try {
          await request({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mese: selectedMonth, value_eur_smc: Number(value), disp: Number(disp) }) });
          await load(); setMessage("PSV del mese selezionato salvato.");
        } catch (error) { setMessage(error instanceof Error ? error.message : "Salvataggio PSV fallito"); }
        finally { setBusy(false); }
      }}>
        <fieldset disabled={busy} className="offerta-fields"><div className="form-grid">
          <label>Mese<select aria-label="Mese" value={selectedMonth} onChange={event => selectMonth(prices, event.target.value)}>
            <option value={prices.current.mese}>{monthLabel(prices.current.mese)} (corrente)</option>
            <option value={prices.previous.mese}>{monthLabel(prices.previous.mese)} (precedente)</option>
          </select></label>
          <label>PSV €/Smc<input type="number" min="0" step="any" required value={value} onChange={event => setValue(event.target.value)} /></label>
          <label>CCR/disp €/Smc<input type="number" min="0" step="any" required value={disp} onChange={event => setDisp(event.target.value)} /></label>
        </div></fieldset>
        <button className="button primary" disabled={busy}>{busy ? "Salvataggio…" : "Salva PSV"}</button>
      </form>
    </>}
    {message && <p role="status" className="alert">{message}</p>}
  </section>;
}
