import { afterEach, describe, expect, it, vi } from "vitest";
import { createElement, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import BillWorkspace from "../components/BillWorkspace";
import type { BillResult } from "./types";

vi.mock("react", async importOriginal => {
  const react = await importOriginal<typeof import("react")>();
  return { ...react, useState: vi.fn(react.useState) };
});

afterEach(() => vi.clearAllMocks());

function render(annual: number, monthly: number) {
  const result: BillResult = {
    bolletta: { kwh_totali: 459, mesi_bolletta: 2, spesa_materia_energia: 127.06,
      spesa_vendita_energia: 105.09, quota_fissa_vendita: 8.34,
      tipo_fornitura: "Luce", tipologia_cliente: "Residenziale" },
    offerte: [{ nome_offerta: "Offerta A", fornitore: "Test", tariffa: "Fisso",
      prezzo_kwh: 0.149, costo_fisso: 12, totale_simulato: 49.62,
      prezzo_effettivo_pagato: 0.2653, differenza_mensile: monthly,
      risparmio_annuo: annual, percentuale: 18.51, tipo_differenza: "Risparmio" }],
  };
  vi.mocked(useState)
    .mockImplementationOnce(() => [null, vi.fn()])
    .mockImplementationOnce(() => [false, vi.fn()])
    .mockImplementationOnce(() => ["", vi.fn()])
    .mockImplementationOnce(() => [result, vi.fn()]);
  const html = renderToStaticMarkup(createElement(BillWorkspace));
  const text = html.replace(/<[^>]*>/g, "").replace(/\s+/g, " ");
  return { html, text };
}

describe("presentazione confronto bolletta", () => {
  it("mostra vendita energia, spesa confrontabile e risparmio annuo verde", () => {
    const { html, text } = render(135.24, -11.27);
    expect(text).toContain("Spesa vendita energia105,09 €");
    expect(text).toContain("Spesa mensile confrontata60,89 €");
    expect(text).not.toContain("127,06");
    expect(text).toContain("RISPARMIO ANNUO STIMATO135,24 €/anno");
    expect(text).toContain("Risparmio mensile di 11,27 €");
    expect(html).toContain('class="offer-price positive"');
  });

  it("mostra il maggior costo annuo rosso senza chiamarlo risparmio", () => {
    const { html, text } = render(-72, 6);
    expect(text).toContain("MAGGIOR COSTO ANNUO STIMATO+ 72,00 €/anno");
    expect(text).toContain("Maggior costo mensile di 6,00 €");
    expect(text).not.toContain("Risparmio mensile");
    expect(html).toContain('class="offer-price negative"');
  });

  it("mostra nessuna differenza quando i costi coincidono", () => {
    const { text } = render(0, 0);
    expect(text).toContain("0,00 €/anno");
    expect(text).toContain("Nessuna differenza");
    expect(text).not.toContain("Maggior costo mensile");
  });
});
