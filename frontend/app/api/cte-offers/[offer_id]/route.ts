import { NextRequest, NextResponse } from "next/server";
export async function PATCH(request: NextRequest, context: { params: Promise<{ offer_id: string }> }) {
  if (request.headers.get("origin") !== request.nextUrl.origin) return NextResponse.json({ detail: "Origine non valida" }, { status: 403 });
  if (!process.env.BACKEND_URL) return NextResponse.json({ detail: "Servizio non configurato" }, { status: 503 });
  const { offer_id } = await context.params;
  try {
    const headers = new Headers({ "Content-Type": "application/json" });
    const cookie = request.headers.get("cookie"); if (cookie) headers.set("cookie", cookie);
    const response = await fetch(`${process.env.BACKEND_URL.replace(/\/+$/, "")}/cte-offers/${encodeURIComponent(offer_id)}`, { method: "PATCH", headers, body: JSON.stringify(await request.json()), signal: AbortSignal.timeout(30_000), cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch { return NextResponse.json({ detail: "Salvataggio non raggiungibile" }, { status: 502 }); }
}
