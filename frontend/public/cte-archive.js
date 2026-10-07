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

export async function mountArchive(target, { request, connection, update }) {
  target.replaceChildren();
  target.append(element("h2", "Archivio CTE"));
  const status = element("p", "Caricamento archivio…"); status.setAttribute("role", "status");
  target.append(status);
  let offers;
  try { offers = (await request()).offers; }
  catch (error) { status.textContent = error.message || "Archivio CTE non disponibile"; return; }
  let sortField = "default", direction = 1;
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
  for (const [value, label] of [["default", "Cliente, fornitore, offerta"], ["supplier", "Fornitore"], ["offer_name", "Nome offerta"], ["customer_type", "Tipologia cliente"], ["supply_type", "Fornitura"], ["tariff_type", "Tariffa"], ["price", "Prezzo / Spread"], ["monthly_fixed_cost", "Quota fissa"], ["min_power_kw", "Potenza minima"], ["max_power_kw", "Potenza massima"], ["valid_until", "Validità"], ["created_at", "Data caricamento"]]) {
    const option = element("option", label); option.value = value; order.append(option);
  }
  const counts = element("p", null, "cte-archive-counts");
  const scroll = element("div", null, "cte-archive-scroll"); scroll.tabIndex = 0; scroll.setAttribute("aria-label", "Tabella CTE attive");
  const table = element("table", null, "cte-archive-table"), head = element("thead"), headings = element("tr"), body = element("tbody");
  const columns = [["supplier", "Fornitore"], ["offer_name", "Offerta"], ["customer_type", "Cliente"], ["supply_type", "Fornitura"], ["tariff_type", "Tariffa"], ["price", "Prezzo / Spread"], ["monthly_fixed_cost", "Quota fissa"], ["min_power_kw", "Potenza minima"], ["max_power_kw", "Potenza massima"], ["valid_until", "Valida fino a"], ["created_at", "Data caricamento"], [null, "Note / Dettagli"], [null, "Azioni"]];
  for (const [field, label] of columns) {
    const th = element("th"); th.scope = "col";
    if (field) {
      th.dataset.sortField = field;
      const button = element("button", label, "cte-sort"); button.type = "button";
      button.addEventListener("click", () => { direction = sortField === field ? -direction : 1; order.value = field; draw(); });
      th.append(button);
    } else th.textContent = label;
    headings.append(th);
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
      const numeric = ["price", "monthly_fixed_cost", "min_power_kw", "max_power_kw"];
      const value = (row, field) => field === "price" ? ((row.tariff_type ?? "").toLowerCase() === "variabile" ? row.spread_kwh : row.fixed_price_kwh) : row[field];
      for (const field of fields) {
        const av = value(a, field), bv = value(b, field);
        if (av == null || bv == null) { if (av !== bv) return av == null ? 1 : -1; continue; }
        const result = numeric.includes(field) ? Number(av) - Number(bv) : String(av).localeCompare(String(bv), "it", { numeric: true });
        if (result) return direction * result;
      }
      return 0;
    });
    status.textContent = rows.length ? `${rows.length} CTE visualizzate` : "Nessuna CTE corrisponde ai filtri.";
    const groups = new Map();
    for (const row of offers) { const key = row.customer_type ?? "Non indicato"; groups.set(key, (groups.get(key) ?? 0) + 1); }
    counts.textContent = `CTE attive: ${offers.length} · ` + [...groups].map(([name, count]) => `${name}: ${count}`).join(" · ");
    for (const th of headings.querySelectorAll("[data-sort-field]")) th.setAttribute("aria-sort", th.dataset.sortField === sortField ? (direction === 1 ? "ascending" : "descending") : "none");
    body.replaceChildren();
    for (const row of rows) {
      const tr = element("tr"); tr.dataset.offerId = row.id;
      const tariff = (row.tariff_type ?? "").toLowerCase();
      tr.className = ["fisso", "fixed", "fissa"].includes(tariff) ? "cte-fixed" : ["variabile", "variable"].includes(tariff) ? "cte-variable" : "";
      for (const value of [row.supplier, row.offer_name, row.customer_type, row.supply_type, ["fisso", "fissa", "fixed"].includes(tariff) ? "Fissa" : ["variabile", "variable"].includes(tariff) ? "Variabile" : row.tariff_type, priceLabel(row), `${euro(row.monthly_fixed_cost)}/mese`, row.min_power_kw == null ? "\u2014" : `${decimal(row.min_power_kw)} kW`, row.max_power_kw == null ? "\u2014" : `${decimal(row.max_power_kw)} kW`, dateLabel(row.valid_until), dateLabel(row.created_at)]) {
        const td = element("td", value ?? "\u2014");
        td.dataset.label = columns[tr.children.length][1];
        tr.append(td);
      }
      const cell = element("td"), details = element("details"); details.append(element("summary", row.notes ? "Note e dettagli" : "Dettagli"));
      if (row.notes) cell.append(element("p", row.notes, "cte-row-notes"));
      details.append(element("p", `Valida dal: ${dateLabel(row.valid_from)}\nCaricata: ${dateLabel(row.created_at)}\nFonte: ${row.source_cte ?? "—"}\nPDF: ${row.pdf_filename ?? "—"}\nPrezzo fisso: ${decimal(row.fixed_price_kwh)}\nSpread: ${decimal(row.spread_kwh)}`));
      cell.append(details); tr.append(cell);
      const actions = element("td");
      if (row.has_pdf) {
        const button = element("button", "Visualizza CTE", "button outline"); button.type = "button";
        button.addEventListener("click", async () => { button.disabled = true; try { await openCtePdf(`/cte-offers/${encodeURIComponent(row.id)}/pdf`, connection()); } catch (error) { status.textContent = error.message; } finally { button.disabled = false; } });
        actions.append(button);
      } else actions.append(element("span", "PDF non disponibile"));
      const edit = element("button", "Modifica", "button outline"); edit.type = "button";
      edit.addEventListener("click", () => editOffer(row, edit)); actions.append(edit);
      tr.append(actions); body.append(tr);
    }
  }
  for (const input of [search, customer, supply, order]) input.addEventListener(input === search ? "input" : "change", draw);
  async function editOffer(row, trigger) {
    const dialog = element("dialog", null, "cte-edit-dialog"), form = element("form"), grid = element("div", null, "cte-edit-grid");
    form.append(element("h2", "Modifica CTE"), element("p", `${row.supplier ?? ""} \u2014 ${row.offer_name ?? ""}`, "muted cte-edit-subtitle"));
    const fields = [["supplier", "Fornitore"], ["offer_name", "Nome offerta"], ["customer_type", "Tipologia cliente"], ["supply_type", "Fornitura"], ["tariff_type", "Tipo tariffa"], ["fixed_price_kwh", "Prezzo fisso"], ["spread_kwh", "Spread"], ["monthly_fixed_cost", "Quota fissa mensile"], ["min_power_kw", "Potenza minima"], ["max_power_kw", "Potenza massima"], ["valid_from", "Valida dal"], ["valid_until", "Valida fino a"], ["source_cte", "Fonte CTE"], ["notes", "Note"]];
    const inputs = new Map();
    for (const [field, label] of fields) {
      const options = field === "supply_type" ? ["Luce", "Gas"] : field === "tariff_type" ? ["Fisso", "Variabile"] : field === "customer_type" ? [...new Set(["Residenziale", "Business", ...offers.map(item => item.customer_type)].filter(Boolean))] : null;
      const input = element(options ? "select" : field === "notes" ? "textarea" : "input"); input.name = field;
      if (options) for (const value of options) { const option = element("option", value === "Fisso" ? "Fissa" : value); option.value = value; input.append(option); }
      if (input.tagName === "INPUT") {
        input.type = field.startsWith("valid_") ? "date" : ["fixed_price_kwh", "spread_kwh", "monthly_fixed_cost", "min_power_kw", "max_power_kw"].includes(field) ? "number" : "text";
        if (input.type === "number") { input.step = "any"; if (field.includes("power")) input.min = "0"; }
      }
      input.required = ["supplier", "offer_name", "customer_type", "supply_type", "tariff_type"].includes(field);
      input.value = row[field] ?? "";
      const wrapper = element("label", label); wrapper.append(input); grid.append(wrapper); inputs.set(field, input);
    }
    const error = element("p"); error.setAttribute("role", "alert");
    const actions = element("div", null, "actions"), cancel = element("button", "Annulla", "button outline"), save = element("button", "Salva modifiche", "button primary");
    cancel.type = "button"; save.type = "submit"; actions.append(cancel, save); form.append(grid, error, actions); dialog.append(form); target.append(dialog);
    const close = () => { dialog.close(); dialog.remove(); trigger.focus(); };
    cancel.addEventListener("click", close);
    let pending = false;
    dialog.addEventListener("cancel", event => { event.preventDefault(); if (!pending) close(); });
    form.addEventListener("submit", async event => {
      event.preventDefault(); if (pending) return;
      const changes = {};
      for (const [field, input] of inputs) { const value = input.value === "" ? null : input.type === "number" ? Number(input.value) : input.value; if (value !== (row[field] ?? null)) changes[field] = value; }
      if (!Object.keys(changes).length) { close(); return; }
      pending = true; save.disabled = cancel.disabled = true; error.textContent = "";
      try {
        await update(row.id, changes);
        offers = (await request()).offers;
        for (const [select, field] of [[customer, "customer_type"], [supply, "supply_type"]]) {
          const previous = select.value;
          select.replaceChildren(); const all = element("option", "Tutte"); all.value = "all"; select.append(all);
          for (const value of [...new Set(offers.map(item => item[field]))].sort((a,b) => (a ?? "").localeCompare(b ?? "", "it"))) {
            const option = element("option", value ?? "Non indicato"); option.value = JSON.stringify(value); select.append(option);
          }
          select.value = [...select.options].some(option => option.value === previous) ? previous : "all";
        }
        draw(); status.textContent = "Modifiche salvate. " + status.textContent; close();
      } catch (cause) { error.textContent = cause.message || "Salvataggio non riuscito"; }
      finally { pending = false; save.disabled = cancel.disabled = false; }
    });
    dialog.showModal();
  }
  order.addEventListener("change", () => { direction = 1; draw(); });
  draw();
}
