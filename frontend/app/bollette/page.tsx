import type { Metadata } from "next";
import PageIntro from "@/components/PageIntro";
import BillWorkspace from "@/components/BillWorkspace";
import MarketPrices from "@/components/MarketPrices";
export const metadata: Metadata = { title: "Confronta bollette" };
export default function BollettePage() {
  return <div className="shell workspace"><PageIntro step="02 / CONFRONTO BOLLETTE" title="La tua bolletta," accent="una nuova prospettiva." description="Carica il PDF della tua bolletta luce o gas. Leggiamo i consumi e confrontiamo le offerte disponibili per la tua fornitura." /><BillWorkspace /><MarketPrices /></div>;
}
