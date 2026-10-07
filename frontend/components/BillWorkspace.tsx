"use client";
import { useRef, useState } from "react";
import { ArrowRight, ArrowDownRight, ArrowUpRight, CheckCircle2, Download, FileText, LoaderCircle, ScanLine, Zap } from "lucide-react";
import UploadZone from "./UploadZone";
import { service, errorMessage, euro, number } from "@/lib/api";
import { readConnection } from "@/lib/connection";
import type { BillResult } from "@/lib/types";

function italianDate(value: string | null | undefined): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value ?? "");
  return match ? `${match[3]}/${match[2]}/${match[1]}` : null;
}

export default function BillWorkspace() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<BillResult | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  async function analyze() {
    if (!file || lock.current) return;
    lock.current = true; setBusy(true); setError(""); setResult(null);
    try {
      const form = new FormData(); form.append("file", file);
      const data = await service<BillResult>("upload-bolletta", form);
      if (!data.bolletta || !Array.isArray(data.offerte)) throw new Error("La risposta non contiene una bolletta e un elenco di offerte validi.");
      const required = [data.bolletta.kwh_totali, data.bolletta.mesi_bolletta, data.bolletta.spesa_vendita_energia, data.bolletta.quota_fissa_vendita];
      if (required.some(value => typeof value !== "number" || !Number.isFinite(value)) || data.bolletta.mesi_bolletta <= 0) throw new Error("I consumi o i costi restituiti dal servizio non sono validi.");
      if (data.offerte.some(offer => [offer.totale_simulato, offer.differenza_mensile, offer.risparmio_annuo, offer.percentuale, offer.prezzo_kwh, offer.costo_fisso].some(value => typeof value !== "number" || !Number.isFinite(value)))) throw new Error("Il servizio ha restituito importi non validi per alcune offerte.");
      setResult({ ...data, offerte: [...data.offerte].sort((a, b) => a.totale_simulato - b.totale_simulato) });
      setTimeout(() => { resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); resultsRef.current?.focus({ preventScroll: true }); }, 100);
    } catch (err) { setError(errorMessage(err)); }
    finally { lock.current = false; setBusy(false); }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "confronto-bolletta.json"; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function openCte(url: string) {
    try {
      const connection = readConnection();
      const target = url.startsWith("http") ? url : `${connection.url.replace(/\/$/, "")}${url}`;
      const response = await fetch(target, { headers: connection.key ? { "x-api-key": connection.key } : undefined });
      if (!response.ok) throw new Error("PDF CTE non disponibile.");
      const objectUrl = URL.createObjectURL(await response.blob());
      window.open(objectUrl, "_blank", "noopener"); setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (err) { setError(errorMessage(err)); }
  }
  const bill = result?.bolletta;
  const unit = bill?.tipo_fornitura.toLowerCase() === "gas" ? "Smc" : "kWh";
  // quota_fissa_vendita is already expressed in EUR/month by extraction.
  const monthly = bill ? bill.spesa_vendita_energia / bill.mesi_bolletta + bill.quota_fissa_vendita : 0;

  return <>
    <div className="work-grid bill-upload-grid"><section className="panel upload-panel"><span className="panel-number">IL TUO PUNTO DI PARTENZA</span><h2>Carica la bolletta</h2><p className="muted">Un PDF è tutto ciò che serve per iniziare il confronto.</p>
      <UploadZone file={file} disabled={busy} onChange={chosen => { setFile(chosen); setError(""); setResult(null); }} label="Trascina qui la tua bolletta" />
      <button className="button primary full" disabled={!file || busy} onClick={() => void analyze()}>{busy ? <><LoaderCircle className="spin" size={18} /> Analisi e confronto in corso…</> : <>Analizza e confronta <ArrowRight size={18} /></>}</button>
      {busy && <p className="processing-message" role="status">Stiamo leggendo il documento e cercando le offerte. L’operazione può richiedere qualche minuto.</p>}
      {error && <div className="alert error" role="alert">{error}</div>}
    </section>
    <aside className="guide-panel"><span className="tiny-label">DAL DOCUMENTO AL CONFRONTO</span><h2>Una lettura più semplice<br />della tua <em>energia.</em></h2><div className="guide-step"><span><ScanLine size={21} /></span><div><h3>Leggiamo la bolletta</h3><p>Estraiamo consumi, periodo e costi della fornitura.</p></div></div><div className="guide-step"><span><Zap size={21} /></span><div><h3>Confrontiamo le offerte</h3><p>Valutiamo le alternative disponibili per la tua tipologia di cliente.</p></div></div><div className="guide-step"><span><CheckCircle2 size={21} /></span><div><h3>Ti mostriamo i numeri</h3><p>Stima mensile e differenza rispetto alla spesa rilevata.</p></div></div><p className="guide-note">Il confronto riguarda la componente energia e la quota fissa di vendita. La stima non rappresenta il totale della bolletta.</p></aside></div>
    {result && bill && <div ref={resultsRef} tabIndex={-1} className="bill-results">
      <div className="result-heading"><div><div className="eyebrow"><span /> ANALISI COMPLETATA</div><h2>I tuoi dati. <em>Le tue possibilità.</em></h2></div><button className="button outline" onClick={download}><Download size={16} /> Scarica risultati JSON</button></div>
      <section className="panel bill-summary"><div className="summary-top"><div><span className="tiny-label">RIEPILOGO BOLLETTA</span><h3>{bill.cliente || "La tua fornitura"}</h3><p className="muted">{bill.indirizzo || "Indirizzo non disponibile"}</p></div><span className="badge">{bill.tipo_fornitura} · {bill.tipologia_cliente}</span></div>
        <div className="stat-grid"><div><span>Consumi del periodo</span><strong>{number(bill.kwh_totali)} <small>{unit}</small></strong></div><div><span>Periodo di fatturazione</span><strong>{number(bill.mesi_bolletta)} <small>mesi</small></strong></div><div><span>Spesa vendita energia</span><strong>{euro(bill.spesa_vendita_energia)}</strong></div><div><span>Spesa mensile confrontata</span><strong className="amber-text">{euro(monthly)}</strong></div></div>
        <div className="summary-foot"><span>POD / PDR: {bill.pod || "Non rilevato"}</span><span>Quota fissa commerciale: {euro(bill.quota_fissa_vendita)}/mese</span></div>
      </section>
      <div className="offers-title"><h3>Offerte a confronto <span>{result.offerte.length}</span></h3><p>Ordinate per costo mensile stimato, dal più basso.</p></div>
      {!result.offerte.length ? <div className="panel empty-state"><FileText size={36} /><h3>Nessuna offerta disponibile</h3><p>Non sono state trovate offerte per questa fornitura e tipologia di cliente. Verifica le offerte archiviate e la loro validità.</p></div> : <div className="offers-grid">{result.offerte.map((offer, index) => {
        const saving = offer.risparmio_annuo > 0;
        const extraCost = offer.risparmio_annuo < 0;
        return <article className={`offer-card ${index === 0 ? "featured" : ""}`} key={`${offer.id ?? offer.nome_offerta}-${index}`}>
          <div className="offer-top"><span className="tool-icon amber"><Zap size={21} /></span><span className="badge">{index === 0 ? "COSTO PIÙ BASSO" : offer.tariffa}</span></div>
          <span className="supplier">{offer.fornitore}</span><h4>{offer.nome_offerta}</h4><span className="tiny-label">{extraCost ? "MAGGIOR COSTO ANNUO STIMATO" : "RISPARMIO ANNUO STIMATO"}</span><div className={`offer-price ${saving ? "positive" : extraCost ? "negative" : ""}`}>{extraCost ? "+ " : ""}{euro(Math.abs(offer.risparmio_annuo))}<small>/anno</small></div>
          <div className={`saving-row ${saving ? "positive" : extraCost ? "negative" : ""}`}>{extraCost ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}<span>{saving ? "Risparmio mensile" : extraCost ? "Maggior costo mensile" : "Nessuna differenza"}{(saving || extraCost) && <> di <strong>{euro(Math.abs(offer.differenza_mensile))}</strong></>}</span></div>
          <dl className="offer-details"><div><dt>Tipo tariffa</dt><dd>{offer.tariffa}</dd></div><div><dt>Prezzo energia</dt><dd>{new Intl.NumberFormat("it-IT", { maximumFractionDigits: 4 }).format(offer.prezzo_kwh)} €/{unit}</dd></div><div><dt>Costo fisso</dt><dd>{euro(offer.costo_fisso)}/mese</dd></div><div><dt>Differenza percentuale</dt><dd>{saving ? "−" : offer.differenza_mensile > 0 ? "+" : ""}{number(Math.abs(offer.percentuale))}%</dd></div></dl>
          {italianDate(offer.valid_until) && <p className="offer-valid-until">Valida fino a: <strong>{italianDate(offer.valid_until)}</strong></p>}
          {offer.notes && <section className="contract-details"><span className="tiny-label">DETTAGLI CONTRATTUALI</span><p>{offer.notes}</p></section>}
          {offer.cte && <button className="button outline full" onClick={() => void openCte(offer.cte!.url)}><FileText size={16} /> Visualizza CTE</button>}
        </article>;
      })}</div>}
      <p className="comparison-note">Le stime usano i consumi e i parametri restituiti dal servizio. Imposte, oneri e trasporto non sono inclusi. Per tariffe variabili, il prezzo dipende anche dall’indice di mercato.</p>
      <details className="json-details"><summary>Visualizza la risposta JSON completa</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
    </div>}
  </>;
}
