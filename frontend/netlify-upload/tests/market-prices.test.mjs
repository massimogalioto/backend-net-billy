// Standalone browser contract test: node netlify-upload/tests/market-prices.test.mjs
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
const require = createRequire(new URL("../../package.json", import.meta.url));
const { chromium } = require("playwright");
const script = await readFile(new URL("../market-prices.js", import.meta.url), "utf8");
const browser = await chromium.launch({ headless: true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
try {
  const page = await browser.newPage();
  page.setDefaultTimeout(6000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  let saved = null;
  let current = { mese: "2026-10", value_eur_smc: null, disp: null, totale: null };
  let previous = { mese: "2026-09", value_eur_smc: 0.8, disp: 0.035, totale: 0.835 };
  await page.route("http://market.test/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/market-prices.js") return route.fulfill({ contentType: "application/javascript", body: script });
    if (url.pathname === "/market-prices-psv") {
      if (route.request().method() === "POST") {
        saved = route.request().postDataJSON();
        if (saved.mese === current.mese) current = { ...saved, totale: 0.855 };
        else previous = { ...saved, totale: 0.855 };
        return route.fulfill({ json: { successo: true } });
      }
      return route.fulfill({ json: { previous, current } });
    }
    return route.fulfill({ contentType: "text/html", body: `<main>Confronto</main><script>sessionStorage.setItem("energia-backend",JSON.stringify({url:"http://market.test",key:""}));</script><script type="module" src="/market-prices.js"></script>` });
  });
  await page.goto("http://market.test/");
  await page.getByRole("button", { name: "Salva PSV" }).waitFor();
  let text = await page.locator("#market-prices-panel").innerText();
  assert.ok(text.includes("settembre 2026"));
  assert.ok(text.includes("0,800 €/Smc"));
  assert.ok(text.includes("0,035 €/Smc"));
  assert.ok(text.includes("0,835 €/Smc"));
  assert.ok(text.includes("Non disponibile"));
  await page.getByLabel("PSV €/Smc", { exact: true }).fill("0.82");
  await page.getByLabel("CCR/disp €/Smc", { exact: true }).fill("0.035");
  await page.getByRole("button", { name: "Salva PSV" }).click();
  await page.getByRole("status").filter({ hasText: "PSV del mese selezionato salvato." }).waitFor();
  assert.deepEqual(saved, { mese: "2026-10", value_eur_smc: 0.82, disp: 0.035 });
  text = await page.locator("#market-prices-panel").innerText();
  assert.ok(text.includes("0,820 €/Smc"));
  assert.ok(text.includes("0,855 €/Smc"));
  await page.getByLabel("Mese", { exact: true }).selectOption("2026-09");
  assert.equal(await page.getByLabel("PSV €/Smc", { exact: true }).inputValue(), "0.8");
  await page.getByLabel("PSV €/Smc", { exact: true }).fill("0.82");
  await page.getByRole("button", { name: "Salva PSV", exact: true }).click();
  await page.waitForFunction(() => !document.querySelector("#market-prices-panel button").disabled);
  assert.equal(saved.mese, "2026-09");
  assert.equal(await page.getByLabel("Mese", { exact: true }).inputValue(), "2026-09");
  assert.equal(await page.getByLabel("Mese", { exact: true }).locator("option").count(), 2);
  assert.deepEqual(errors, []);
  console.log("PASS: PSV previous/current display, Italian units, missing month, manual save and refresh.");
} finally {
  await browser.close();
}
