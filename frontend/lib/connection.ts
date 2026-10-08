export const directConnection = process.env.NEXT_PUBLIC_STATIC_MODE === "true";
const defaultBackendUrl = "https://backend-net-billy-production.up.railway.app";
export function readConnection(): { url: string } { return { url: (process.env.NEXT_PUBLIC_BACKEND_URL ?? defaultBackendUrl).replace(/\/+$/, "") }; }
export function connectionRequest(url: string, init: RequestInit): [string, RequestInit] {
  if (!directConnection) return [url, init];
  const connection = readConnection();
  const endpoint = url.split("/").pop();
  const headers = new Headers(init.headers);
  return [`${connection.url}/${endpoint}`, { ...init, headers, credentials: "include" }];
}
