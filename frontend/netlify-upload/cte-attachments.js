// Attachment support for this Netlify export. Never stores provider credentials.
const retries = new WeakMap();

async function originalPdf(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const chunks = [];
  for (let offset = 0; offset < bytes.length; offset += 16384) {
    chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 16384)));
  }
  return { filename: file.name, content_base64: btoa(chunks.join("")) };
}

export async function saveCte(file, offer, url, connectionRequest) {
  if (!(file instanceof File)) throw new Error("Il PDF originale della CTE non è più disponibile. Seleziona nuovamente il documento.");
  const previous = retries.get(file);
  const signature = JSON.stringify(offer);
  if (previous && previous.signature !== signature) {
    throw new Error(`Record Airtable già creato: ${previous.recordId}. Per riprovare l'allegato mantieni i dati originali dell'offerta.`);
  }
  const payload = { ...offer, cte_pdf: await originalPdf(file) };
  if (previous) payload.cte_retry_token = previous.token;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 300000);
  try {
    const response = await fetch(...connectionRequest(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload), signal: controller.signal,
    }));
    let result;
    try { result = await response.json(); }
    catch { throw new Error(`Risposta del servizio non leggibile (HTTP ${response.status})`); }
    if (!response.ok) {
      if (response.status === 409 && result.detail === "CTE già presente") throw new Error("Questa CTE risulta già presente nel tuo archivio.");
      const detail = result.detail;
      if (detail?.fase === "attachment" && detail.record_id && detail.cte_retry_token) {
        retries.set(file, { signature, recordId: detail.record_id, token: detail.cte_retry_token });
      }
      const error = new Error(typeof detail === "string" ? detail : detail?.message ?? `Errore HTTP ${response.status}`);
      error.recordId = detail?.record_id ?? previous?.recordId ?? null;
      throw error;
    }
    if (!result.successo || !result.id) throw new Error("Salvataggio Airtable e attachment CTE non confermati");
    retries.delete(file);
    return result;
  } catch (error) {
    if (controller.signal.aborted) throw new Error("Timeout: il PDF o il record potrebbero essere già salvati. Verifica Airtable prima di riprovare.");
    throw error;
  } finally { clearTimeout(timeout); }
}

export function showCte(cte, offerName) {
  let url;
  try { url = new URL(cte.url); } catch { return; }
  if (url.protocol !== "https:" || url.username || url.password) return;
  const dialog = document.createElement("dialog");
  dialog.setAttribute("aria-label", `CTE - ${offerName}`);
  Object.assign(dialog.style, { width: "94vw", maxWidth: "1100px", height: "90vh", padding: "20px" });
  const title = document.createElement("h2");
  title.textContent = `CTE - ${offerName}`;
  const close = document.createElement("button");
  close.className = "button outline";
  close.type = "button";
  close.textContent = "Chiudi CTE";
  close.addEventListener("click", () => dialog.close());
  const fallback = document.createElement("a");
  fallback.className = "button outline";
  fallback.href = url.href;
  fallback.target = "_blank";
  fallback.rel = "noopener noreferrer";
  fallback.textContent = "Apri PDF in una nuova scheda";
  const note = document.createElement("p");
  note.textContent = `${cte.filename}. Se il PDF non appare, aprilo in una nuova scheda. Se il link è scaduto, ripeti il confronto per aggiornarlo.`;
  const frame = document.createElement("iframe");
  frame.title = cte.filename;
  frame.referrerPolicy = "no-referrer";
  frame.src = url.href;
  Object.assign(frame.style, { width: "100%", height: "calc(100% - 180px)", border: "0", marginTop: "16px" });
  dialog.append(title, close, fallback, note, frame);
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  document.body.append(dialog);
  dialog.showModal();
  close.focus();
}
