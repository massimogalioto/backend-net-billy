import { connectionRequest } from "./lib/connection";
export const MAX_CONCURRENT = 2;
export type Status = "IN ATTESA" | "ELABORAZIONE" | "SALVATAGGIO" | "COMPLETATA" | "ERRORE";
export type Result = {
  filename: string; success: boolean; output_ai: Record<string, unknown> | null;
  airtable_id: string | null; error: string | null; correctable?: boolean;
  validation_errors?: { field: string; message: string }[];
};
export type Item = Result & { file: File; status: Status; id: number };

export type ValidationResponse = { status: "validation_error"; message: string; errors: { field: string; message: string }[]; extracted_data: Record<string, unknown> };
export class ValidationError extends Error {
  constructor(public readonly validation: ValidationResponse) { super(validation.message); }
}

export function selectPdfs(files: File[]): Item[] {
  return files.filter(file => /\.pdf$/i.test(file.name)).map((file, id) => ({
    file, id, filename: file.name, status: "IN ATTESA", success: false,
    output_ai: null, airtable_id: null, error: null,
  }));
}

async function request(url: string, init: RequestInit) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 300_000);
  try {
    const response = await fetch(...connectionRequest(url, { ...init, signal: controller.signal }));
    let data;
    try { data = await response.json(); } catch { throw new Error(`Risposta del servizio non leggibile (HTTP ${response.status})`); }
    if (response.status === 409 && data.detail === "CTE già presente") throw new Error("Questa CTE risulta già presente nel tuo archivio.");
    if (!response.ok) {
      if (response.status === 422 && data && typeof data === "object" && (data as { status?: string }).status === "validation_error") throw new ValidationError(data as ValidationResponse);
      const detail = data.message ?? data.detail;
      throw new Error(typeof detail === "string" ? detail : `Errore HTTP ${response.status}: ${JSON.stringify(detail)}`);
    }
    return data;
  } catch (error) {
    if (controller.signal.aborted) throw new Error("Timeout: verificare PostgreSQL e Bucket prima di riprovare un salvataggio.");
    throw error;
  } finally { clearTimeout(timer); }
}

async function pdfPayload(file: File) {
  const content_base64 = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader(); reader.onerror = () => reject(new Error("Impossibile leggere il PDF CTE."));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? ""); reader.readAsDataURL(file);
  });
  return { filename: file.name, content_base64 };
}

export async function saveManualCorrection(item: Item, baseUrl: string, corrected: Record<string, unknown>) {
  return request(`${baseUrl}/salva-offerta-manuale`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...corrected, fonte_cte: corrected.fonte_cte || item.filename, cte_pdf: await pdfPayload(item.file) }),
  });
}

// Only MAX_CONCURRENT workers are started, each handling extraction AND saving.
export async function runBatch(items: Item[], baseUrl: string, update: (id: number, patch: Partial<Item>) => void) {
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const item = items[next++];
      let output = item.output_ai;
      update(item.id, { status: "ELABORAZIONE", error: null });
      try {
        // Preserve successful extraction when retrying a failed save.
        if (!output) {
          if (!item.file.size || item.file.size > 25 * 1024 * 1024) throw new Error("Il PDF deve avere una dimensione compresa tra 1 byte e 25 MB");
          const form = new FormData(); form.append("file", item.file);
          const extracted = await request(`${baseUrl}/upload-cte`, { method: "POST", body: form });
          if (!extracted.output_ai || typeof extracted.output_ai !== "object" || Array.isArray(extracted.output_ai)) throw new Error("Risposta AI non valida");
          if (extracted.output_ai.errore) throw new Error(extracted.output_ai.errore);
          output = { ...extracted.output_ai, fonte_cte: item.filename };
        }
        update(item.id, { status: "SALVATAGGIO", output_ai: output });
        const saved = await request(`${baseUrl}/salva-offerta`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...output, cte_pdf: await pdfPayload(item.file) }),
        });
        if (!saved.successo || !saved.id) throw new Error("Salvataggio PostgreSQL non confermato");
        update(item.id, { status: "COMPLETATA", success: true, output_ai: output, airtable_id: saved.id, error: null });
      } catch (error) {
        const validation = error instanceof ValidationError ? error.validation : null;
        update(item.id, { status: "ERRORE", success: false, output_ai: validation?.extracted_data ?? output, airtable_id: null,
          correctable: !!validation, validation_errors: validation?.errors,
          error: error instanceof Error ? error.message : "Errore inatteso" });
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(MAX_CONCURRENT, items.length) }, worker));
}
