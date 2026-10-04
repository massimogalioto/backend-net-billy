import { test, expect, Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const offer = (name: string) => ({ fornitore: "Same supplier", nome_offerta: name, tipologia_cliente: "Residenziale", tariffa: "Fisso", tipo_fornitura: "Luce", prezzo_kwh: 0.12, costo_fisso: 12, spread: 0, validita: "2026-10-31" });
const pdf = (marker: string) => Buffer.from(`%PDF-1.4\n${marker}\n%%EOF`);
async function configure(page: Page) {
  await page.goto("/cte/");
  await page.getByLabel("URL backend HTTPS").fill("https://backend.test");
  await page.getByLabel("Chiave API del backend").fill("test-key");
  await page.getByRole("button", { name: "Salva collegamento" }).click();
}

test("CTE singola invia il PDF originale insieme all'offerta corretta", async ({ page }) => {
  let saved: any;
  const original = pdf("EDISON_ORIGINAL");
  await page.route("https://backend.test/**", async route => {
    if (route.request().url().endsWith("upload-cte")) {
      expect(route.request().postDataBuffer()!.includes(original)).toBe(true);
      await route.fulfill({ json: { output_ai: offer("Edison Dynamic") }, headers: { "Access-Control-Allow-Origin": "*" } });
    } else {
      saved = route.request().postDataJSON();
      expect(route.request().headers()["x-api-key"]).toBe("test-key");
      await route.fulfill({ json: { successo: true, id: "recEdison" }, headers: { "Access-Control-Allow-Origin": "*" } });
    }
  });
  await configure(page);
  await page.getByLabel("Seleziona PDF", { exact: true }).setInputFiles({ name: "test_edison.pdf", mimeType: "application/pdf", buffer: original });
  await page.getByRole("button", { name: "Estrai i dati della CTE" }).click();
  await page.getByRole("button", { name: "Salva offerta in Airtable" }).click();
  await expect(page.getByText("Offerta salvata correttamente.")).toBeVisible();
  expect(saved.nome_offerta).toBe("Edison Dynamic");
  expect(saved.cte_pdf.filename).toBe("test_edison.pdf");
  expect(Buffer.from(saved.cte_pdf.content_base64, "base64")).toEqual(original);
});

test("massivo mantiene concorrenza 2, distingue PDF omonimi e ritenta solo l'attachment fallito", async ({ page }, info) => {
  const originals = { FILE_A: pdf("FILE_A"), FILE_B: pdf("FILE_B"), FILE_C: pdf("FILE_C") };
  let active = 0, peak = 0, failed = false;
  const uploads: string[] = [], saves: any[] = [];
  // Playwright omits disk-backed multipart file bodies from request.postData.
  // Read the exact selected File in the browser to identify mocked OCR results.
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      if (String(input).endsWith("upload-cte") && init?.body instanceof FormData) {
        const file = init.body.get("file") as File;
        const marker = /FILE_[ABC]/.exec(await file.text())?.[0];
        const headers = new Headers(init.headers);
        if (marker) headers.set("x-test-pdf-marker", marker);
        return nativeFetch(input, { ...init, headers });
      }
      return nativeFetch(input, init);
    };
  });
  await page.route("https://backend.test/**", async route => {
    const request = route.request();
    let result: any, status = 200;
    if (request.url().endsWith("upload-cte")) {
      active++; peak = Math.max(peak, active);
      const marker = request.headers()["x-test-pdf-marker"];
      expect(marker).toMatch(/^FILE_[ABC]$/);
      uploads.push(marker);
      await new Promise(resolve => setTimeout(resolve, 60));
      result = { output_ai: offer(marker) };
    } else {
      const data = request.postDataJSON();
      saves.push(data);
      expect(Buffer.from(data.cte_pdf.content_base64, "base64")).toEqual(originals[data.nome_offerta as keyof typeof originals]);
      if (!data.cte_retry_token) active--;
      if (data.nome_offerta === "FILE_B" && !failed) {
        failed = true; status = 502;
        result = { detail: { fase: "attachment", record_id: "recFILE_B", cte_retry_token: "recFILE_B.signed-test", message: "Upload attachment fallito: shared.pdf - Timeout. Record Airtable conservato: recFILE_B" } };
      } else result = { successo: true, id: `rec${data.nome_offerta}` };
    }
    await route.fulfill({ status, json: result, headers: { "Access-Control-Allow-Origin": "*" } });
  });
  await configure(page);
  await page.getByRole("tab", { name: "Caricamento massivo" }).click();
  const folder = info.outputPath("documents");
  for (const [subdir, filename, marker] of [["a", "shared.pdf", "FILE_A"], ["b", "shared.pdf", "FILE_B"], ["c", "third.pdf", "FILE_C"]]) {
    mkdirSync(join(folder, subdir), { recursive: true });
    writeFileSync(join(folder, subdir, filename), originals[marker as keyof typeof originals]);
  }
  await page.locator('input[webkitdirectory]').setInputFiles(folder);
  await page.getByRole("button", { name: "ELABORA TUTTE LE CTE" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Totale: 3" })).toContainText("Completate: 2 — Errori: 1");
  expect(peak).toBe(2);
  expect(uploads).toHaveLength(3);
  await expect(page.locator(".batch-list li").filter({ hasText: "b/shared.pdf" })).toContainText("recFILE_B");
  await page.getByRole("button", { name: "Riprova errori" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Totale: 3" })).toContainText("Completate: 3 — Errori: 0");
  expect(uploads).toHaveLength(3);
  expect(saves).toHaveLength(4);
  expect(saves[3].cte_retry_token).toBe("recFILE_B.signed-test");
  expect(saves[3].nome_offerta).toBe("FILE_B");
});

test("confronto mostra solo le CTE presenti, apre il PDF specifico e permette chiusura e fallback", async ({ page }) => {
  const jsErrors: string[] = [];
  page.on("pageerror", error => jsErrors.push(error.message));
  const result = {
    bolletta: { kwh_totali: 1200, mesi_bolletta: 2, spesa_materia_energia: 300, quota_fissa_vendita: 24, tipo_fornitura: "Luce", tipologia_cliente: "Residenziale" },
    offerte: [
      { id: 7, ...offer("Fixed"), totale_simulato: 96, differenza_mensile: -66, percentuale: 40.74, cte: { filename: "fixed.pdf", url: "https://attachments.test/recFIXED/fixed.pdf" } },
      { id: 8, ...offer("Variable"), totale_simulato: 108, differenza_mensile: -54, percentuale: 33.33, cte: { filename: "variable.pdf", url: "https://attachments.test/recVARIABLE/variable.pdf" } },
      { id: 9, ...offer("No PDF"), totale_simulato: 142, differenza_mensile: -20, percentuale: 12.35, cte: null },
    ],
  };
  await page.route("https://backend.test/**", route => route.fulfill({ json: result, headers: { "Access-Control-Allow-Origin": "*" } }));
  await page.route("https://attachments.test/**", route => route.fulfill({ contentType: "application/pdf", body: pdf(route.request().url()) }));
  await configure(page);
  // Exercise Next client navigation as well as the updated static navigation payloads.
  await page.getByRole("link", { name: "Confronta bollette", exact: true }).click();
  await expect(page).toHaveURL(/\/bollette\/$/);
  await expect(page.getByRole("heading", { name: "Carica la bolletta", exact: true })).toBeVisible();
  await page.getByLabel("Seleziona PDF", { exact: true }).setInputFiles({ name: "bill.pdf", mimeType: "application/pdf", buffer: pdf("BILL") });
  await page.getByRole("button", { name: "Analizza e confronta" }).click();
  await expect(page.locator(".offer-card")).toHaveCount(3);
  await expect(page.getByRole("button", { name: "Visualizza CTE" })).toHaveCount(2);
  await expect(page.locator(".offer-card").filter({ hasText: "No PDF" }).getByRole("button", { name: "Visualizza CTE" })).toHaveCount(0);
  await expect(page.locator("dialog")).toHaveCount(0);
  const first = page.locator(".offer-card").filter({ hasText: "Fixed" });
  await expect(first.locator(".offer-price")).toContainText("96,00");
  await first.getByRole("button", { name: "Visualizza CTE" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.locator("dialog iframe")).toHaveAttribute("src", "https://attachments.test/recFIXED/fixed.pdf");
  const fallback = page.getByRole("link", { name: "Apri PDF in una nuova scheda" });
  await expect(fallback).toHaveAttribute("href", "https://attachments.test/recFIXED/fixed.pdf");
  await expect(fallback).toHaveAttribute("target", "_blank");
  await page.getByRole("button", { name: "Chiudi CTE" }).click();
  await expect(page.locator("dialog")).toHaveCount(0);
  await page.locator(".offer-card").filter({ hasText: "Variable" }).getByRole("button", { name: "Visualizza CTE" }).click();
  await expect(page.locator("dialog iframe")).toHaveAttribute("src", "https://attachments.test/recVARIABLE/variable.pdf");
  await page.keyboard.press("Escape");
  await expect(page.locator("dialog")).toHaveCount(0);
  expect(jsErrors).toEqual([]);
});
