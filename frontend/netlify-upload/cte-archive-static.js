import { mountArchive } from "./cte-archive.js";
const root = document.querySelector(".shell.workspace");
if (root) {
  const uploadNodes = [...root.children];
  let states = uploadNodes.map(node => node.hidden);
  const nav = document.createElement("nav"); nav.className = "cte-archive-nav"; nav.setAttribute("aria-label", "Area CTE");
  const upload = document.createElement("button"), archive = document.createElement("button");
  upload.type = archive.type = "button"; upload.textContent = "Carica CTE"; archive.textContent = "Archivio CTE";
  nav.append(upload, archive);
  const panel = document.createElement("section"); panel.className = "panel"; panel.hidden = true; panel.id = "cte-archive";
  root.prepend(nav); root.append(panel);
  function connection() {
    const fallback = { url: "https://backend-net-billy-production.up.railway.app", key: "" };
    try { return { ...fallback, ...JSON.parse(sessionStorage.getItem("energia-backend") || "{}") }; } catch { return fallback; }
  }
  function select(showArchive) {
    if (showArchive && panel.hidden) states = uploadNodes.map(node => node.hidden);
    uploadNodes.forEach((node, index) => { node.hidden = showArchive || states[index]; });
    panel.hidden = !showArchive;
    upload.className = `button ${showArchive ? "outline" : "primary"}`;
    archive.className = `button ${showArchive ? "primary" : "outline"}`;
    upload.setAttribute("aria-pressed", String(!showArchive)); archive.setAttribute("aria-pressed", String(showArchive));
    if (showArchive) mountArchive(panel, { connection, request: async () => {
      const settings = connection();
      const response = await fetch(`${settings.url.replace(/\/+$/, "")}/cte-offers`, { headers: settings.key ? { "x-api-key": settings.key } : undefined, signal: AbortSignal.timeout(30_000) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Archivio CTE non disponibile"); return data;
    } });
  }
  upload.addEventListener("click", () => select(false)); archive.addEventListener("click", () => select(true)); select(false);
}
