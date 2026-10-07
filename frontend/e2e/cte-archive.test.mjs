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
const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
try {
  const page = await browser.newPage(); page.setDefaultTimeout(8000);
  const errors = []; let pdfRequested = false;
  page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(() => { window.open = (...args) => { window.pdfOpenArgs = args; return null; }; });
  await page.route("http://archive.test/**", async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith(".js") || pathname.endsWith(".css")) {
      const name = pathname.substring(1);
      return route.fulfill({ contentType: name.endsWith(".js") ? "application/javascript" : "text/css", body: await readFile(new URL(`../public/${name}`, import.meta.url), "utf8") });
    }
    if (pathname === "/cte-offers") return route.fulfill({ json: { offers: rows } });
    if (pathname === "/cte-offers/a/pdf") { pdfRequested = true; return route.fulfill({ contentType: "application/pdf", body: "%PDF-1.4 test" }); }
    return route.fulfill({ contentType: "text/html", body: `<link rel="stylesheet" href="/cte-archive.css"><main><div class="shell workspace"><div>Upload esistente</div></div></main><script>sessionStorage.setItem("energia-backend",JSON.stringify({url:"http://archive.test",key:""}));</script><script type="module" src="/cte-archive-static.js"></script>` });
  });
  await page.goto("http://archive.test/");
  await page.getByRole("button", { name: "Archivio CTE", exact: true }).click();
  await page.locator("tbody tr").first().waitFor();
  assert.equal(await page.locator("tbody tr").count(), 3);
  const content = await page.locator("table").innerText();
  for (const value of ["0,149 €/kWh", "PSV + 0,1 €/Smc", "PUN + 0,015 €/kWh", "≥ 25 kW", "≤ 15 kW", "10–30 kW", "31/10/2026", "Non indicata"]) assert.ok(content.includes(value), value);
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
  await page.setViewportSize({ width: 375, height: 800 });
  assert.ok(await page.locator(".cte-archive-scroll").evaluate(node => node.scrollWidth > node.clientWidth));
  await page.getByRole("button", { name: "Carica CTE", exact: true }).click();
  assert.ok(await page.getByText("Upload esistente", { exact: true }).isVisible());
  assert.deepEqual(errors, []);
  console.log("PASS: archive table, dynamic filters, sorting, search, prices/power/dates, safe notes, mobile scroll, shared PDF and upload navigation.");
} finally { await browser.close(); }
