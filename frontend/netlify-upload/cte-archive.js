import { openCtePdf } from "./cte-pdf.js";

const decimal = value => value == null ? "—" : new Intl.NumberFormat("it-IT", { maximumFractionDigits: 6 }).format(value);
const euro = value => value == null ? "—" : new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(value);
const dateLabel = value => value ? new Intl.DateTimeFormat("it-IT", { timeZone: "UTC" }).format(new Date(value.length === 10 ? `${value}T00:00:00Z` : value)) : "Non indicata";
export function powerLabel(row) {
  const min = row.min_power_kw, max = row.max_power_kw;
  if (min == null && max == null) return "—";
  if (min == null) return `≤ ${decimal(max)} kW`;
  if (max == null) return `≥ ${decimal(min)} kW`;
  return `${decimal(min)}–${decimal(max)} kW`;
}
export function priceLabel(row) {
  const gas = (row.supply_type ?? "").toLowerCase() === "gas";
  const unit = gas ? "€/Smc" : "€/kWh";
  if ((row.tariff_type ?? "").toLowerCase() === "variabile") {
    return row.spread_kwh == null ? "—" : `${gas ? "PSV" : "PUN"} + ${decimal(row.spread_kwh)} ${unit}`;
  }
  return row.fixed_price_kwh == null ? "—" : `${decimal(row.fixed_price_kwh)} ${unit}`;
}
const element = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (className) node.className = className;
  return node;
};

export async function mountArchive(target, { request, connection }) {
  target.replaceChildren();
  target.append(element("h2", "Archivio CTE"));
  const status = element("p", "Caricamento archivio…"); status.setAttribute("role", "status");
  target.append(status);
  let offers;
  try { offers = (await request()).offers; }
  catch (error) { status.textContent = error.message || "Archivio CTE non disponibile"; return; }
  let sortField = "default";
  const controls = element("div", null, "cte-archive-toolbar");
  function control(label, node) { const wrapper = element("label", label); wrapper.append(node); controls.append(wrapper); return node; }
  const search = control("Cerca fornitore o offerta", element("input")); search.type = "search"; search.placeholder = "Cerca fornitore o offerta…";
  function filter(label, field) {
    const select = control(label, element("select")); select.setAttribute("aria-label", label);
    const all = element("option", "Tutte"); all.value = "all"; select.append(all);
    for (const value of [...new Set(offers.map(row => row[field]))].sort((a, b) => (a ?? "").localeCompare(b ?? "", "it"))) {
      const option = element("option", value ?? "Non indicato"); option.value = JSON.stringify(value); select.append(option);
    }
    return select;
  }
  const customer = filter("Tipologia cliente", "customer_type"), supply = filter("Fornitura", "supply_type");
  const order = control("Ordina per", element("select")); order.setAttribute("aria-label", "Ordina per");
  for (const [value, label] of [["default", "Cliente, fornitore, offerta"], ["supplier", "Fornitore"], ["offer_name", "Nome offerta"], ["customer_type", "Tipologia cliente"], ["supply_type", "Fornitura"], ["valid_until", "Validità"], ["created_at", "Data caricamento"]]) {
    const option = element("option", label); option.value = value; order.append(option);
  }
  const counts = element("p", null, "cte-archive-counts");
  const scroll = element("div", null, "cte-archive-scroll"); scroll.tabIndex = 0; scroll.setAttribute("aria-label", "Tabella CTE attive");
  const table = element("table", null, "cte-archive-table"), head = element("thead"), headings = element("tr"), body = element("tbody");
  for (const label of ["Fornitore", "Offerta", "Cliente", "Fornitura", "Tariffa", "Prezzo / Spread", "Quota fissa", "Potenza", "Valida fino a", "Note / Dettagli", "Azioni"]) {
    const th = element("th", label); th.scope = "col"; headings.append(th);
  }
  head.append(headings); table.append(head, body); scroll.append(table);
  target.append(controls, counts, scroll);
  function draw() {
    sortField = order.value;
    const query = search.value.trim().toLocaleLowerCase("it");
    const rows = offers.filter(row => (customer.value === "all" || JSON.stringify(row.customer_type) === customer.value)
      && (supply.value === "all" || JSON.stringify(row.supply_type) === supply.value)
      && `${row.supplier ?? ""} ${row.offer_name ?? ""}`.toLocaleLowerCase("it").includes(query));
    rows.sort((a, b) => {
      const fields = sortField === "default" ? ["customer_type", "supplier", "offer_name"] : [sortField, "supplier", "offer_name"];
      for (const field of fields) { const result = (a[field] ?? "\uffff").toString().localeCompare((b[field] ?? "\uffff").toString(), "it", { numeric: true }); if (result) return result; }
      return 0;
    });
    status.textContent = rows.length ? `${rows.length} CTE visualizzate` : "Nessuna CTE corrisponde ai filtri.";
    const groups = new Map();
    for (const row of offers) { const key = row.customer_type ?? "Non indicato"; groups.set(key, (groups.get(key) ?? 0) + 1); }
    counts.textContent = `CTE attive: ${offers.length} · ` + [...groups].map(([name, count]) => `${name}: ${count}`).join(" · ");
    body.replaceChildren();
    for (const row of rows) {
      const tr = element("tr"); tr.dataset.offerId = row.id;
      for (const value of [row.supplier, row.offer_name, row.customer_type, row.supply_type, row.tariff_type, priceLabel(row), `${euro(row.monthly_fixed_cost)}/mese`, powerLabel(row), dateLabel(row.valid_until)]) tr.append(element("td", value ?? "—"));
      const cell = element("td"), details = element("details"); details.append(element("summary", row.notes ? "Note e dettagli" : "Dettagli"));
      if (row.notes) details.append(element("p", row.notes));
      details.append(element("p", `Valida dal: ${dateLabel(row.valid_from)}\nCaricata: ${dateLabel(row.created_at)}\nFonte: ${row.source_cte ?? "—"}\nPDF: ${row.pdf_filename ?? "—"}\nPrezzo fisso: ${decimal(row.fixed_price_kwh)}\nSpread: ${decimal(row.spread_kwh)}`));
      cell.append(details); tr.append(cell);
      const actions = element("td");
      if (row.has_pdf) {
        const button = element("button", "Visualizza CTE", "button outline"); button.type = "button";
        button.addEventListener("click", async () => { button.disabled = true; try { await openCtePdf(`/cte-offers/${encodeURIComponent(row.id)}/pdf`, connection()); } catch (error) { status.textContent = error.message; } finally { button.disabled = false; } });
        actions.append(button);
      } else actions.append(element("span", "PDF non disponibile"));
      tr.append(actions); body.append(tr);
    }
  }
  for (const input of [search, customer, supply, order]) input.addEventListener(input === search ? "input" : "change", draw);
  draw();
}
