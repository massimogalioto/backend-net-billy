import Link from "next/link";
import PageIntro from "@/components/PageIntro";
import CteArchive from "@/components/CteArchive";
export const metadata = { title: "Archivio CTE" };
export default function ArchivePage() {
  return <div className="shell workspace"><PageIntro step="01 / CONDIZIONI ECONOMICHE" title="Archivio CTE" accent="in essere." description="Consulta le offerte attive del tuo archivio." />
    <nav className="cte-archive-nav" aria-label="Area CTE"><Link className="button outline" href="/cte">Carica CTE</Link><Link className="button primary" aria-current="page" href="/cte/archivio">Archivio CTE</Link></nav>
    <CteArchive /></div>;
}
