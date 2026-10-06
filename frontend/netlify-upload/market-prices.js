// Isolated PSV panel for the existing static export; does not modify bill or CTE flows.
export const formatPrice = value => new Intl.NumberFormat("it-IT", {
  minimumFractionDigits: 3, maximumFractionDigits: 8,
}).format(value);

function connection() {
  const fallback = { url: "https://backend-net-billy-production.up.railway.app", key: "" };
  try { return { ...fallback, ...JSON.parse(sessionStorage.getItem("energia-backend") || "{}") }; }
  catch { return fallback; }
}

export async function mountMarketPrices(target, request = async init => {
  const settings = connection();
  const headers = new Headers(init?.headers);
  if (settings.key) headers.set("x-api-key", settings.key);
  const response = await fetch(`${settings.url.replace(/\/+$/, "")}/market-prices-psv`, {
    ...init, headers, signal: AbortSignal.timeout(30000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Prezzi PSV non disponibili");
  return data;
}) {
  target.className = "panel";
  target.setAttribute("aria-label", "Prezzi mercato PSV");
  target.innerHTML = `<h2>Prezzi mercato</h2>
    <p class="muted">PSV mensile e CCR per il confronto gas. Se il mese corrente manca, usiamo il mese precedente.</p>
    <div class="stat-grid" data-prices></div>
    <form hidden><fieldset class="offerta-fields"><div class="form-grid">
      <label>Mese<select name="mese" aria-label="Mese"></select></label>
      <label>PSV €/Smc<input name="value_eur_smc" type="number" min="0" step="any" required></label>
      <label>CCR/disp €/Smc<input name="disp" type="number" min="0" step="any" required></label>
    </div></fieldset><button class="button primary">Salva PSV</button></form>
    <p class="alert" role="status" hidden></p>`;
  const form = target.querySelector("form");
  const message = target.querySelector('[role="status"]');
  const showMessage = text => { message.textContent = text; message.hidden = false; };
  let data;
  function selectMonth() {
    const row = form.elements.mese.value === data.previous.mese ? data.previous : data.current;
    form.elements.value_eur_smc.value = row.value_eur_smc ?? "";
    form.elements.disp.value = row.disp ?? "";
  }
  form.elements.mese.addEventListener("change", selectMonth);
  async function load() {
    const selected = form.elements.mese.value;
    data = await request();
    const grid = target.querySelector("[data-prices]");
    grid.replaceChildren();
    for (const row of [data.previous, data.current]) {
      const card = document.createElement("div");
      const month = new Intl.DateTimeFormat("it-IT", { month: "long", year: "numeric", timeZone: "UTC" })
        .format(new Date(`${row.mese}-01T00:00:00Z`));
      const title = document.createElement("span"); title.textContent = `PSV ${month}`;
      const values = document.createElement("p");
      values.textContent = row.value_eur_smc === null ? "Non disponibile"
        : `${formatPrice(row.value_eur_smc)} €/Smc · CCR/disp: ${formatPrice(row.disp ?? 0)} €/Smc · Totale: ${formatPrice(row.totale)} €/Smc`;
      card.append(title, values); grid.append(card);
    }
    form.elements.mese.replaceChildren();
    for (const [row, label] of [[data.current, "corrente"], [data.previous, "precedente"]]) {
      const option = document.createElement("option"); option.value = row.mese;
      option.textContent = `${row.mese} (${label})`; form.elements.mese.append(option);
    }
    if ([data.current.mese, data.previous.mese].includes(selected)) form.elements.mese.value = selected;
    selectMonth();
    form.hidden = false;
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = form.querySelector("button");
    if (button.disabled) return;
    button.disabled = true; form.querySelector("fieldset").disabled = true;
    try {
      await request({ method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mese: form.elements.mese.value,
          value_eur_smc: Number(form.elements.value_eur_smc.value), disp: Number(form.elements.disp.value) }) });
      await load(); showMessage("PSV del mese selezionato salvato.");
    } catch (error) { showMessage(error.message || "Salvataggio PSV fallito"); }
    finally { button.disabled = false; form.querySelector("fieldset").disabled = false; }
  });
  try { await load(); } catch (error) { showMessage(error.message || "Prezzi PSV non disponibili"); }
}

if (typeof document !== "undefined") {
  const main = document.querySelector("main");
  if (main && !document.getElementById("market-prices-panel")) {
    const wrapper = document.createElement("div"); wrapper.className = "shell";
    wrapper.style.marginBlock = "24px";
    const panel = document.createElement("section"); panel.id = "market-prices-panel";
    wrapper.append(panel); main.after(wrapper);
    mountMarketPrices(panel);
  }
}
