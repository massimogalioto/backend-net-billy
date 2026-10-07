import type { Metadata } from "next";
import PageIntro from "@/components/PageIntro";
import CteWorkspace from "@/components/CteWorkspace";
import Link from "next/link";
export const metadata: Metadata = { title: "Carica CTE" };
export default function CtePage() {
  return <div className="shell workspace"><PageIntro step="01 / CONDIZIONI ECONOMICHE" title="Le tue offerte," accent="in chiaro." description="Carica una CTE, controlla i dati estratti e salvala. Hai più documenti? Elabora un’intera cartella con il caricamento massivo." /><nav aria-label="Area CTE" style={{ display: "flex", gap: 12, marginBottom: 18 }}><Link className="button primary" aria-current="page" href="/cte">Carica CTE</Link><Link className="button outline" href="/cte/archivio">Archivio CTE</Link></nav><CteWorkspace /></div>;
}
