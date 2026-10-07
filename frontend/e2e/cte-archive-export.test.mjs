import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
const require = createRequire(new URL("../package.json", import.meta.url));
const { chromium } = require("playwright");
const rows = [
  { id: "a", supplier: "Edison", offer_name: "Alpha", customer_type: "Domestico", supply_type: "Luce", tariff_type: "Fisso", fixed_price_kwh: 0.149, spread_kwh: null, monthly_fixed_cost: 12, min_power_kw: 25, max_power_kw: null, valid_until: "2026-10-31", notes: "Fatturazione: Mensile\n<img src=x onerror=alert(1)>", has_pdf: true },
  { id: "b", supplier: "Beta", offer_name: "Gas", customer_type: "Altri usi", supply_type: "Gas", tariff_type: "Variabile", fixed_price_kwh: null, spread_kwh: 0.1, monthly_fixed_cost: 10, min_power_kw: null, max_power_kw: 15, valid_until: null, notes: null, has_pdf: false },
  { id: "c", supplier: "Gamma", offer_name: "Condominio", customer_type: "Condominio", supply_type: "Luce", tariff_type: "Variabile", fixed_price_kwh: null, spread_kwh: 0.015, monthly_fixed_cost: 15, min_power_kw: 10, max_power_kw: 30, valid_until: "2026-11-01", notes: null, has_pdf: false },
];
import { spawn } from "node:child_process";
const server = spawn(process.execPath, ["scripts/serve-static.mjs"], { env: process.env, stdio: "ignore", windowsHide: true });
for(let i=0;i<80;i++){try{if((await fetch("http://127.0.0.1:4173/")).ok)break;}catch{}await new Promise(resolve=>setTimeout(resolve,100));}
const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
try {
  const page = await browser.newPage(); page.setDefaultTimeout(8000);
  const errors = []; let pdfRequested = false;
  page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(() => { window.open = (...args) => { window.pdfOpenArgs = args; return null; }; });
  await page.route("https://backend-net-billy-production.up.railway.app/**", async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/cte-offers/a" && route.request().method() === "PATCH") {
      Object.assign(rows[0], route.request().postDataJSON());
      return route.fulfill({ headers: { "Access-Control-Allow-Origin": "*" }, json: { status: "updated" } });
    }
    if (pathname === "/cte-offers") return route.fulfill({ headers: { "Access-Control-Allow-Origin": "*" }, json: { offers: rows.filter(row => !row.valid_until || row.valid_until >= "2026-10-07") } });
    if (pathname === "/cte-offers/a/pdf") { pdfRequested = true; return route.fulfill({ headers: { "Access-Control-Allow-Origin": "*" }, contentType: "application/pdf", body: "%PDF-1.4 test" }); }
    if (route.request().method() === "OPTIONS") return route.fulfill({ headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET,PATCH,OPTIONS", "Access-Control-Allow-Headers": "content-type,x-api-key" }, body: "" });
    return route.abort();
  });
  await page.goto("http://127.0.0.1:4173/");
  await page.locator('a[href="/cte"],a[href="/cte/"]').first().click();
  await page.getByRole("link", { name: "Archivio CTE", exact: true }).click();
  await page.locator("tbody tr").first().waitFor();
  assert.equal(await page.locator("tbody tr").count(), 3);
  const content = await page.locator("table").innerText();
  for (const value of ["0,149 €/kWh", "PSV + 0,1 €/Smc", "PUN + 0,015 €/kWh", "25 kW", "15 kW", "30 kW", "31/10/2026", "Non indicata"]) assert.ok(content.includes(value), value);
  assert.equal(await page.locator("table img").count(), 0);
  await page.getByLabel("Tipologia cliente", { exact: true }).selectOption(JSON.stringify("Domestico"));
  assert.equal(await page.locator("tbody tr").count(), 1);
  await page.getByRole("button", { name: "Visualizza CTE", exact: true }).click();
  await page.waitForFunction(() => !!window.pdfOpenArgs);
  assert.ok(pdfRequested);
  assert.deepEqual(await page.evaluate(() => window.pdfOpenArgs.slice(1)), ["_blank", "noopener"]);
  await page.getByLabel("Tipologia cliente", { exact: true }).selectOption("all");
  await page.getByLabel("Fornitura", { exact: true }).selectOption(JSON.stringify("Gas"));
  assert.equal(await page.locator("tbody tr").count(), 1);
  assert.ok((await page.locator("tbody tr").innerText()).includes("Beta"));
  await page.getByLabel("Fornitura", { exact: true }).selectOption("all");
  await page.getByPlaceholder("Cerca fornitore o offerta…").fill("gamma");
  assert.equal(await page.locator("tbody tr").count(), 1);
  await page.getByPlaceholder("Cerca fornitore o offerta…").fill("");
  await page.getByLabel("Ordina per", { exact: true }).selectOption("supplier");
  assert.ok((await page.locator("tbody tr").first().innerText()).startsWith("Beta"));
  for (const field of ["supplier", "customer_type", "supply_type", "tariff_type", "valid_until", "price", "monthly_fixed_cost", "min_power_kw", "max_power_kw", "created_at", "offer_name"]) {
    const header = page.locator(`th[data-sort-field="${field}"]`);
    await header.getByRole("button").click();
    assert.ok(["ascending", "descending"].includes(await header.getAttribute("aria-sort")));
    const before = await page.locator("tbody tr").evaluateAll(nodes => nodes.map(node => node.dataset.offerId));
    await header.getByRole("button").click();
    const after = await page.locator("tbody tr").evaluateAll(nodes => nodes.map(node => node.dataset.offerId));
    if (!["created_at"].includes(field)) assert.notDeepEqual(before, after, field);
  }
  await page.locator('tr[data-offer-id="a"]').getByRole("button", { name: "Modifica", exact: true }).click();
  assert.equal(await page.locator('dialog input[name="valid_until"]').inputValue(), "2026-10-31");
  assert.equal(await page.locator('dialog input[name="supplier"]').inputValue(), "Edison");
  await page.locator('dialog input[name="valid_until"]').fill("2026-11-30");
  await page.locator('dialog textarea[name="notes"]').fill("First\nSecond");
  await page.getByRole("button", { name: "Salva modifiche" }).click();
  await page.waitForFunction(() => !document.querySelector("dialog"));
  await page.locator('tr[data-offer-id="a"]').getByRole("button", { name: "Visualizza CTE", exact: true }).click();
  assert.equal(rows[0].valid_until, "2026-11-30"); assert.equal(rows[0].notes, "First\nSecond");
  assert.ok((await page.locator('tr[data-offer-id="a"]').innerText()).includes("30/11/2026"));
  await page.locator('tr[data-offer-id="a"]').getByRole("button", { name: "Modifica", exact: true }).click();
  await page.locator('dialog input[name="valid_until"]').fill("2026-10-01");
  await page.getByRole("button", { name: "Salva modifiche" }).click();
  await page.waitForFunction(() => !document.querySelector("dialog"));
  assert.equal(await page.locator('tr[data-offer-id="a"]').count(), 0);
  await page.setViewportSize({ width: 375, height: 800 });
  assert.ok(await page.locator(".cte-archive-scroll").evaluate(node => node.scrollWidth > node.clientWidth));
  await page.reload(); await page.locator("tbody tr").first().waitFor();
  await page.getByRole("navigation", { name: "Area CTE" }).getByRole("link", { name: "Carica CTE", exact: true }).click();
  await page.getByRole("link", { name: "Archivio CTE", exact: true }).waitFor();
  assert.deepEqual(errors, []);
  console.log("PASS: archive table, dynamic filters, sorting, search, prices/power/dates, safe notes, mobile scroll, shared PDF and upload navigation.");
} finally { await browser.close(); server.kill(); }
