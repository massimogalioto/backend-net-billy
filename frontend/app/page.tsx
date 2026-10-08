import Link from "next/link";
import { UsageSummary } from "@/components/UsageSummary";
import { ArrowRight, ArrowUpRight, FileText, FolderOpen, ScanLine, ShieldCheck, Sparkles, Zap } from "lucide-react";

export default function Home() {
  return <>
    <UsageSummary />
    <section className="hero">
      <div className="hero-landscape" aria-hidden="true" />
      <div className="shell hero-grid">
        <div className="hero-copy"><div className="eyebrow"><span /> IL TUO SPAZIO PER L’ENERGIA</div>
          <h1>Meno complessità.<br />Più <em>chiarezza.</em></h1>
          <p>Le offerte e le bollette, finalmente nello stesso posto. Trasforma i tuoi documenti in informazioni utili e trova la soluzione più adatta.</p>
          <div className="hero-actions"><Link href="/bollette" className="button primary">Confronta la tua bolletta <ArrowUpRight size={18} /></Link><Link href="/cte" className="text-link">Gestisci le CTE <ArrowRight size={16} /></Link></div>
          <div className="hero-note"><span className="cyan-dot" /><span>DA UN PDF A UNA SCELTA INFORMATA<small>Un percorso semplice, per luce e gas.</small></span></div>
        </div>
        <aside className="quick-card"><div className="quick-kicker"><Sparkles size={17} /> PARTIAMO DA QUI</div><h2>Cosa vuoi fare?</h2><p>Scegli il tuo prossimo passo.</p>
          <Link href="/cte" className="quick-option warm"><span className="option-icon"><FolderOpen size={24} /></span><span><strong>Carica CTE</strong><small>Organizza le tue offerte energetiche</small></span><ArrowUpRight size={20} /></Link>
          <Link href="/bollette" className="quick-option"><span className="option-icon"><ScanLine size={24} /></span><span><strong>Confronta bollette</strong><small>Scopri le alternative per la tua fornitura</small></span><ArrowUpRight size={20} /></Link>
          <div className="quick-foot"><ShieldCheck size={16} /><span>Analisi dei documenti, senza inserimenti manuali.</span></div>
        </aside>
      </div>
      <div className="hero-bottom shell"><span>DOCUMENTI. DATI. DECISIONI.</span><span>SCOPRI IL WORKSPACE <span className="down-arrow">↓</span></span></div>
    </section>
    <section className="shell home-tools"><div className="section-heading"><div><div className="eyebrow"><span /> DUE STRUMENTI, UN SOLO SPAZIO</div><h2>La tua energia.<br /><em>Sotto controllo.</em></h2></div><p>Carica un documento, verifica i dati e passa all’azione. Tutto quello che ti serve, senza passaggi superflui.</p></div>
      <div className="tool-grid">
        <Link href="/cte" className="tool-card"><div className="tool-top"><span className="tool-icon amber"><FileText size={25} /></span><span className="tiny-label">01 / OFFERTE</span></div><h3>Carica CTE</h3><p>Estrai le condizioni economiche dai PDF, verifica i dettagli e salva le offerte nel tuo archivio.</p><div className="tool-features"><span>Upload singolo</span><span>Caricamento cartella</span><span>Salvataggio Airtable</span></div><div className="tool-bottom"><span>Vai alle condizioni economiche</span><ArrowUpRight size={23} /></div></Link>
        <Link href="/bollette" className="tool-card cyan-card"><div className="tool-top"><span className="tool-icon cyan"><Zap size={25} /></span><span className="tiny-label">02 / CONFRONTO</span></div><h3>Confronta bollette</h3><p>Leggi i consumi della tua bolletta e confronta le offerte disponibili con una stima mensile trasparente.</p><div className="tool-features"><span>Analisi PDF</span><span>Riepilogo consumi</span><span>Confronto offerte</span></div><div className="tool-bottom"><span>Trova la tua prossima offerta</span><ArrowUpRight size={23} /></div></Link>
      </div>
    </section>
    <section className="shell process-strip"><div><span>01</span><strong>Carica il documento</strong><p>Il tuo PDF, singolo o in cartella.</p></div><div><span>02</span><strong>Leggi i dati</strong><p>Le informazioni essenziali, in chiaro.</p></div><div><span>03</span><strong>Scegli il prossimo passo</strong><p>Salva un’offerta o confronta i costi.</p></div></section>
  </>;
}
