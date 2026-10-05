import { describe, expect, it, vi, afterEach } from "vitest";
import { Item, runBatch, selectPdfs } from "./cte-batch";

afterEach(() => vi.unstubAllGlobals());
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const offer = { fornitore: "Test", nome_offerta: "Test" };

async function exercise(names: string[], brokenPdf = "", brokenSave = "") {
  let active = 0, peak = 0;
  const items = selectPdfs(names.map(name => new File(["pdf"], name)));
  const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
    if (url.endsWith("upload-cte")) {
      active++; peak = Math.max(peak, active);
      await new Promise(resolve => setTimeout(resolve, 5));
      const name = (init.body as FormData).get("file") as File;
      if (name.name === brokenPdf) { active--; return response({ detail: "PDF corrotto" }, 500); }
      return response({ filename: name.name, output_ai: offer });
    }
    const data = JSON.parse(init.body as string);
    active--;
    return data.fonte_cte === brokenSave
      ? response({ detail: "Airtable non disponibile" }, 500)
      : response({ successo: true, id: `rec-${data.fonte_cte}` });
  });
  vi.stubGlobal("fetch", fetchMock);
  const update = (id: number, patch: Partial<Item>) => Object.assign(items[id], patch);
  await runBatch(items, "/api/cte", update);
  return { items, peak, fetchMock, update };
}

describe("coda CTE", () => {
  it("mostra un messaggio specifico per una CTE duplicata", async () => {
    const items = selectPdfs([new File(["pdf"], "duplicate.pdf")]);
    items[0].output_ai = offer;
    vi.stubGlobal("fetch", vi.fn(async () => response({ detail: "CTE già presente", existing_offer_id: "existing" }, 409)));
    await runBatch(items, "/api/service", (id, patch) => Object.assign(items[id], patch));
    expect(items[0].success).toBe(false);
    expect(items[0].error).toBe("Questa CTE risulta già presente nel tuo archivio.");
  });
  it("non salva risposte AI con errore e continua con gli altri PDF", async () => {
    const items = selectPdfs(["bad.pdf", "ok.pdf"].map(name => new File(["pdf"], name)));
    const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
      if (url.endsWith("upload-cte")) {
        const file = (init.body as FormData).get("file") as File;
        return response({ output_ai: file.name === "bad.pdf" ? { errore: "AI fallita" } : offer });
      }
      return response({ successo: true, id: "rec-ok" });
    });
    vi.stubGlobal("fetch", fetchMock);
    await runBatch(items, "/api/service", (id, patch) => Object.assign(items[id], patch));
    expect(items[0].error).toBe("AI fallita");
    expect(items[1].status).toBe("COMPLETATA");
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith("salva-offerta"))).toHaveLength(1);
  });
  it("salva tre PDF e imposta fonte_cte", async () => {
    const { items } = await exercise(["a.pdf", "b.pdf", "c.pdf"]);
    expect(items.every(item => item.success && item.airtable_id && item.output_ai?.fonte_cte === item.filename)).toBe(true);
  });
  it("isola un PDF corrotto", async () => {
    const { items } = await exercise(["a.pdf", "bad.pdf", "c.pdf"], "bad.pdf");
    expect(items.filter(item => item.success)).toHaveLength(2);
    expect(items[1].error).toBe("PDF corrotto");
  });
  it("ignora JPG e TXT e accetta PDF maiuscolo", () => {
    expect(selectPdfs(["a.PDF", "a.jpg", "a.txt"].map(name => new File([], name)))).toHaveLength(1);
  });
  it("continua dopo errore Airtable e limita la concorrenza", async () => {
    const { items, peak } = await exercise(["a.pdf", "bad.pdf", "c.pdf", "d.pdf"], "", "bad.pdf");
    expect(items.filter(item => item.success)).toHaveLength(3);
    expect(peak).toBe(2);
  });
  it("riprova solo gli errori riutilizzando l'estrazione", async () => {
    const { items, fetchMock, update } = await exercise(["a.pdf", "bad.pdf", "c.pdf"], "", "bad.pdf");
    fetchMock.mockClear();
    fetchMock.mockImplementation(async () => response({ successo: true, id: "rec-retry" }));
    await runBatch(items.filter(item => item.status === "ERRORE"), "/api/cte", update);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/cte/salva-offerta");
    expect(items.every(item => item.success)).toBe(true);
  });
});
