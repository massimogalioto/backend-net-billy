export const directConnection = process.env.NEXT_PUBLIC_STATIC_MODE === "true";
const storageKey = "energia-backend";
const defaultBackendUrl = "https://backend-net-billy-production.up.railway.app";
export function readConnection(): { url: string; key: string } {
  const fallback = { url: process.env.NEXT_PUBLIC_BACKEND_URL ?? defaultBackendUrl, key: "" };
  if (typeof window === "undefined") return fallback;
  try { return { ...fallback, ...JSON.parse(sessionStorage.getItem(storageKey) ?? "{}") }; }
  catch { return fallback; }
}
export function saveConnection(url: string, key: string) {
  const parsed = new URL(url);
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash) throw new Error("Inserisci un URL HTTP/HTTPS valido senza credenziali, query o frammenti.");
  if (location.protocol === "https:" && parsed.protocol !== "https:") throw new Error("Il backend deve usare HTTPS quando il sito usa HTTPS.");
  sessionStorage.setItem(storageKey, JSON.stringify({ url: url.replace(/\/+$/, ""), key }));
}
export function connectionRequest(url: string, init: RequestInit): [string, RequestInit] {
  if (!directConnection) return [url, init];
  const connection = readConnection();
  if (!connection.url) throw new Error("Configura prima il collegamento al backend nella parte superiore della pagina.");
  const endpoint = url.split("/").pop();
  const headers = new Headers(init.headers);
  if (connection.key) headers.set("x-api-key", connection.key);
  return [`${connection.url.replace(/\/+$/, "")}/${endpoint}`, { ...init, headers, credentials: "omit" }];
}
