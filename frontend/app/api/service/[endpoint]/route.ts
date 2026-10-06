import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 300;
const allowed = new Set(["upload-cte", "upload-bolletta", "salva-offerta", "salva-offerta-manuale", "confronta", "market-prices-psv"]);
const MAX_FILE_BYTES = 25 * 1024 * 1024;

export async function GET(request: NextRequest, context: { params: Promise<{ endpoint: string }> }) {
  const { endpoint } = await context.params;
  if (endpoint !== "market-prices-psv") return NextResponse.json({ detail: "Endpoint non disponibile" }, { status: 404 });
  if (!process.env.BACKEND_URL) return NextResponse.json({ detail: "Collegamento al servizio non configurato" }, { status: 503 });
  try {
    const headers = new Headers();
    if (process.env.API_SECRET_KEY) headers.set("x-api-key", process.env.API_SECRET_KEY);
    const response = await fetch(`${process.env.BACKEND_URL.replace(/\/$/, "")}/${endpoint}`, { headers, cache: "no-store", signal: AbortSignal.timeout(30_000) });
    return NextResponse.json(await response.json(), { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: "Prezzi PSV non raggiungibili" }, { status: 502 });
  }
}

export async function POST(request: NextRequest, context: { params: Promise<{ endpoint: string }> }) {
  const { endpoint } = await context.params;
  if (!allowed.has(endpoint)) return NextResponse.json({ detail: "Endpoint non disponibile" }, { status: 404 });
  const origin = request.headers.get("origin");
  if (!origin || origin !== request.nextUrl.origin) return NextResponse.json({ detail: "Origine della richiesta non valida" }, { status: 403 });
  if (!process.env.BACKEND_URL) return NextResponse.json({ detail: "Collegamento al servizio non configurato" }, { status: 503 });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 290_000);
  try {
    const headers = new Headers();
    if (process.env.API_SECRET_KEY) headers.set("x-api-key", process.env.API_SECRET_KEY);
    let body: FormData | string;
    if (endpoint.startsWith("upload-")) {
      const form = await request.formData();
      const file = form.get("file");
      if (!(file instanceof File) || !/\.pdf$/i.test(file.name)) return NextResponse.json({ detail: "Seleziona un file PDF" }, { status: 400 });
      if (!file.size || file.size > MAX_FILE_BYTES) return NextResponse.json({ detail: "Il PDF deve avere una dimensione compresa tra 1 byte e 25 MB" }, { status: 413 });
      body = new FormData(); body.append("file", file);
    } else {
      body = JSON.stringify(await request.json());
      headers.set("Content-Type", "application/json");
    }
    const backend = await fetch(`${process.env.BACKEND_URL.replace(/\/$/, "")}/${endpoint}`, { method: "POST", headers, body, signal: controller.signal, cache: "no-store" });
    const raw = await backend.text();
    let data: unknown;
    try { data = JSON.parse(raw); }
    catch { return NextResponse.json({ detail: `Il servizio ha restituito una risposta non valida (HTTP ${backend.status})` }, { status: 502 }); }
    return NextResponse.json(data, { status: backend.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: controller.signal.aborted ? "Tempo massimo superato. Se stavi salvando, verifica PostgreSQL e Bucket prima di riprovare." : "Servizio non raggiungibile. Riprova tra poco." }, { status: controller.signal.aborted ? 504 : 502 });
  } finally { clearTimeout(timeout); }
}
