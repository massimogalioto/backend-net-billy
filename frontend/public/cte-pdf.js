// Existing PDF-opening flow shared by comparison and archive.
export async function openCtePdf(url, connection) {
  const target = url.startsWith("http") ? url : `${connection.url.replace(/\/$/, "")}${url}`;
  const response = await fetch(target, { headers: connection.key ? { "x-api-key": connection.key } : undefined });
  if (!response.ok) throw new Error("PDF CTE non disponibile.");
  const objectUrl = URL.createObjectURL(await response.blob());
  window.open(objectUrl, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}
