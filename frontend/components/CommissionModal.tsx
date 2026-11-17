"use client";
import { useEffect, useRef, useState } from "react";
import { LoaderCircle, X } from "lucide-react";
import { errorMessage, euro, service } from "@/lib/api";
import type { Confronto } from "@/lib/types";

type Band = { min_contracts: number; max_contracts: number | null; base_amount: string; sepa_bonus: string };
type Item = { cte_offer_id: string; supplier: string; offer_name: string; bands: Band[] };

export default function CommissionModal({ offers, onClose }: { offers: Confronto[]; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const node = dialog.current; node?.showModal();
    void service<{ offers: Item[] }>("cte-commissions-query", { offer_ids: offers.map(item => item.id) })
      .then(data => setItems(data.offers)).catch(err => setError(errorMessage(err)));
    return () => node?.close();
  }, [offers]);
  const byId = new Map((items ?? []).map(item => [item.cte_offer_id, item]));
  return <dialog ref={dialog} className="commission-dialog" onClose={onClose} onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className="commission-head"><div><span className="tiny-label">DATI COMMERCIALI RISERVATI</span><h2>Provvigioni delle offerte</h2></div><button className="icon-button" aria-label="Chiudi" onClick={onClose}><X /></button></div>
    <p className="muted">Importi indicativi secondo le fasce configurate. La provvigione effettiva dipende dalle condizioni del mandato commerciale.</p>
    {error ? <div className="alert error" role="alert">{error}</div> : !items ? <div className="commission-loading"><LoaderCircle className="spin" /> Caricamento provvigioni…</div> :
      <div className="commission-table-wrap"><table className="commission-table"><thead><tr><th>Fornitore</th><th>Offerta</th><th>Fascia</th><th>Base</th><th>Bonus SEPA</th><th>Totale SEPA</th><th /></tr></thead><tbody>{offers.map(offer => {
        const item = offer.id ? byId.get(offer.id) : undefined; const first = item?.bands[0];
        return <tr key={offer.id}><td>{offer.fornitore}</td><td>{offer.nome_offerta}</td>{first ? <><td>{first.min_contracts}–{first.max_contracts ?? "∞"}</td><td>{euro(Number(first.base_amount))}</td><td>+{euro(Number(first.sepa_bonus))}</td><td>{euro(Number(first.base_amount) + Number(first.sepa_bonus))}</td><td><details><summary>Dettagli fasce</summary><div className="band-details">{item!.bands.map(band => <div key={`${band.min_contracts}-${band.max_contracts}`}><span>{band.min_contracts}–{band.max_contracts ?? "∞"}</span><span>{euro(Number(band.base_amount))}</span><span>+{euro(Number(band.sepa_bonus))}</span><strong>{euro(Number(band.base_amount) + Number(band.sepa_bonus))}</strong></div>)}</div></details></td></> : <td colSpan={5}>Provvigione non configurata</td>}</tr>;
      })}</tbody></table></div>}
  </dialog>;
}
