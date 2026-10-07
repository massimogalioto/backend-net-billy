"use client";
import { useRef, useState } from "react";
import { ArrowRight, CheckCircle2, Database, FileCheck2, FolderOpen, LoaderCircle } from "lucide-react";
import UploadZone from "./UploadZone";
import CaricamentoMassivoCTE from "@/CaricamentoMassivoCTE";
import { service, errorMessage } from "@/lib/api";
import type { Offerta } from "@/lib/types";

const empty: Offerta = { fornitore: "", nome_offerta: "", tipologia_cliente: "", tariffa: "", prezzo_kwh: null, spread: null, costo_fisso: null, valid_from: null, valid_until: null, fonte_cte: "", vincoli: "", notes: "", tipo_fornitura: "" };
const numeric = new Set(["prezzo_kwh", "spread", "costo_fisso"]);
const fields: { key: keyof Offerta; label: string; required?: boolean; type?: string; options?: string[] }[] = [
  { key: "fornitore", label: "Fornitore", required: true }, { key: "nome_offerta", label: "Nome offerta", required: true },
  { key: "tipo_fornitura", label: "Fornitura", required: true, options: ["Luce", "Gas"] }, { key: "tipologia_cliente", label: "Tipologia cliente", required: true, options: ["Residenziale", "Business"] },
  { key: "tariffa", label: "Tipo tariffa", required: true, options: ["Fisso", "Variabile"] }, { key: "valid_from", label: "Inizio validità (se indicato)", type: "date" }, { key: "valid_until", label: "Valida fino a", type: "date" },
  { key: "prezzo_kwh", label: "Prezzo fisso (€/kWh o €/Smc)", type: "number" }, { key: "spread", label: "Spread (€/kWh o €/Smc)", type: "number" },
  { key: "costo_fisso", label: "Costo fisso mensile (€)", type: "number" }, { key: "fonte_cte", label: "Fonte CTE" }, { key: "vincoli", label: "Note e vincoli" },
  { key: "notes", label: "Dettagli contrattuali", type: "textarea" },
];

export default function CteWorkspace() {
  const [mode, setMode] = useState("single");
  const [file, setFile] = useState<File | null>(null);
  const [offerta, setOfferta] = useState<Offerta | null>(null);
  const [busy, setBusy] = useState<"extract" | "save" | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<string | null>(null);

  async function extract() {
    if (!file || lock.current) return;
    lock.current = true; setBusy("extract"); setError(""); setOfferta(null); setSaved(null);
    try {
      const form = new FormData(); form.append("file", file);
      const data = await service<{ output_ai: Partial<Offerta> & { errore?: string } }>("upload-cte", form);
      if (!data.output_ai || Array.isArray(data.output_ai) || typeof data.output_ai !== "object") throw new Error("Il servizio non ha restituito dati CTE validi.");
      if (data.output_ai.errore) throw new Error(data.output_ai.errore);
      const extracted = { ...empty };
      for (const field of fields) {
        const value = data.output_ai[field.key];
        if (value != null) Object.assign(extracted, { [field.key]: numeric.has(field.key) ? (Number.isFinite(Number(value)) ? Number(value) : null) : String(value) });
      }
      extracted.fonte_cte = "";
      for (const field of ["valid_from", "valid_until"] as const) if (extracted[field] && !/^\d{4}-\d{2}-\d{2}$/.test(extracted[field])) extracted[field] = null;
      setOfferta(extracted);
    } catch (err) { setError(errorMessage(err)); }
    finally { lock.current = false; setBusy(null); }
  }
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!offerta || lock.current || saved) return;
    lock.current = true; setBusy("save"); setError("");
    try {
      if (!file) throw new Error("PDF CTE originale non disponibile.");
      const content_base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader(); reader.onerror = () => reject(new Error("Impossibile leggere il PDF CTE."));
        reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? ""); reader.readAsDataURL(file);
      });
      const result = await service<{ successo: boolean; id: string }>("salva-offerta", { ...offerta, cte_pdf: { filename: file.name, content_base64 } });
      if (!result.successo || !result.id) throw new Error("Il salvataggio non è stato confermato dal servizio.");
      setSaved(result.id);
    } catch (err) { setError(errorMessage(err)); }
    finally { lock.current = false; setBusy(null); }
  }
  return <>
    <div className="mode-switch" role="tablist" aria-label="Modalità caricamento CTE">
      <button id="single-tab" role="tab" aria-selected={mode === "single"} aria-controls="single-panel" disabled={!!busy || batchBusy} onClick={() => setMode("single")}><FileCheck2 size={18} /> CTE singola</button>
      <button id="batch-tab" role="tab" aria-selected={mode === "batch"} aria-controls="batch-panel" disabled={!!busy || batchBusy} onClick={() => setMode("batch")}><FolderOpen size={18} /> Caricamento massivo</button>
    </div>
    <div id="single-panel" role="tabpanel" aria-labelledby="single-tab" hidden={mode !== "single"}>
      <div className="work-grid"><section className="panel upload-panel"><span className="panel-number">PASSO 01</span><h2>Carica il documento</h2><p className="muted">Seleziona le condizioni tecnico economiche dell’offerta.</p>
        <UploadZone file={file} disabled={!!busy} onChange={chosen => { setFile(chosen); setOfferta(null); setSaved(null); setError(""); }} label="Trascina qui la tua CTE" />
        <button className="button primary full" disabled={!file || !!busy} onClick={() => void extract()}>{busy === "extract" ? <><LoaderCircle className="spin" size={18} /> Analisi in corso…</> : <>Estrai i dati della CTE <ArrowRight size={18} /></>}</button>
        <div className="panel-note"><Database size={17} /><span>Le offerte vengono salvate nel tuo archivio dopo la verifica dei dati.</span></div>
      </section>
      <section className="panel result-panel"><span className="panel-number">PASSO 02</span><h2>Verifica e salva</h2><p className="muted">Controlla le condizioni estratte prima del salvataggio.</p>
        {!offerta ? <div className="empty-state">{busy === "extract" ? <LoaderCircle size={42} className="spin" /> : <FileCheck2 size={42} />}<h3>{busy === "extract" ? "Stiamo leggendo la tua CTE" : "Qui prenderà forma la tua offerta"}</h3><p>{busy === "extract" ? "L’analisi può richiedere qualche minuto. Mantieni aperta la pagina." : "Carica un PDF per visualizzare fornitore, prezzi e condizioni."}</p><div className="empty-lines"><i /><i /><i /></div></div>
          : <form onSubmit={save}><fieldset disabled={!!busy || !!saved} className="offerta-fields"><div className="form-grid">{fields.map(field => <label key={field.key} className={field.key === "vincoli" || field.key === "notes" ? "span-two" : ""}>{field.label}{field.required && <span className="required"> *</span>}
            {field.options ? <select value={offerta[field.key] ?? ""} required={field.required} onChange={event => setOfferta({ ...offerta, [field.key]: event.target.value })}><option value="">Seleziona…</option>{field.options.map(option => <option key={option}>{option}</option>)}</select>
              : field.type === "textarea" ? <textarea rows={4} value={offerta[field.key] ?? ""} onChange={event => setOfferta({ ...offerta, [field.key]: event.target.value || null })} />
              : <input type={field.type ?? "text"} required={field.required} min={field.type === "number" ? "0" : undefined} step={field.type === "number" ? "any" : undefined} value={offerta[field.key] ?? ""} onChange={event => setOfferta({ ...offerta, [field.key]: numeric.has(field.key) ? (event.target.value === "" ? null : Number(event.target.value)) : (event.target.value || null) })} />}
          </label>)}</div></fieldset>
          <p className="form-note">* Campi obbligatori. Inserisci manualmente la fonte della CTE.</p>
          {saved ? <div className="alert success" role="status"><CheckCircle2 size={19} /><span>Offerta salvata correttamente.<small>Riferimento: {saved}</small></span></div> : <button className="button primary full" disabled={!!busy} type="submit">{busy === "save" ? <><LoaderCircle className="spin" size={18} /> Salvataggio…</> : <><Database size={18} /> Salva offerta</>}</button>}
        </form>}
      </section></div>
    </div>
    <div id="batch-panel" role="tabpanel" aria-labelledby="batch-tab" hidden={mode !== "batch"} className="panel batch-panel"><CaricamentoMassivoCTE baseUrl="/api/service" onRunningChange={setBatchBusy} /></div>
    {error && <div className="alert error" role="alert">{error}</div>}
  </>;
}
