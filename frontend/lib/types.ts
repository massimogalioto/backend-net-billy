export type Offerta = {
  fornitore: string; nome_offerta: string; tipologia_cliente: string; tariffa: string;
  prezzo_kwh: number | null; spread: number | null; costo_fisso: number | null;
  validita: string | null; fonte_cte: string | null; vincoli: string | null; tipo_fornitura: string;
};
export type Bolletta = {
  cliente?: string; indirizzo?: string; pod?: string; kwh_totali: number;
  mesi_bolletta: number; spesa_materia_energia: number; spesa_vendita_energia: number; quota_fissa_vendita: number;
  tipo_fornitura: string; tipologia_cliente: string;
};
export type Confronto = {
  id?: string; fornitore: string; nome_offerta: string; tariffa: string;
  prezzo_kwh: number; costo_fisso: number; totale_simulato: number;
  prezzo_effettivo_pagato: number; differenza_mensile: number; risparmio_annuo: number; tipo_differenza: string; percentuale: number;
  cte?: { filename: string; url: string } | null;
};
export type BillResult = { bolletta: Bolletta; offerte: Confronto[] };
