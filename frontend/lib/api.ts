import { connectionRequest } from "./connection";
export async function service<T>(endpoint: string, body: FormData | object): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 300_000);
  try {
    const multipart = body instanceof FormData;
    const response = await fetch(...connectionRequest(`/api/service/${endpoint}`, {
      method: "POST", body: multipart ? body : JSON.stringify(body),
      headers: multipart ? undefined : { "Content-Type": "application/json" }, signal: controller.signal,
    }));
    let data;
    try { data = await response.json(); } catch { throw new Error(`Risposta del servizio non leggibile (HTTP ${response.status})`); }
    if (!response.ok || data.errore) {
      const detail = data.detail ?? data.errore;
      throw new Error(typeof detail === "string" ? detail + (data.mancanti ? `: ${data.mancanti.join(", ")}` : "") : JSON.stringify(detail ?? `Errore HTTP ${response.status}`));
    }
    return data;
  } catch (error) {
    if (controller.signal.aborted) throw new Error("Tempo massimo superato. Verifica PostgreSQL e Bucket prima di riprovare un salvataggio.");
    throw error;
  } finally { clearTimeout(timer); }
}
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Si è verificato un errore. Riprova.";
export const euro = (value: number) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(value);
export const number = (value: number) => new Intl.NumberFormat("it-IT", { maximumFractionDigits: 2 }).format(value);
