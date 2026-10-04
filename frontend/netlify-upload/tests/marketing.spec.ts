import { test, expect } from "@playwright/test";

test("landing, piani e navigazione verso l'anteprima", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Il comparatore intelligente per broker energetici.");
  for (const amount of ["14,99", "44,99"]) await expect(page.getByText(amount, { exact: false }).first()).toBeVisible();
  await page.getByRole("link", { name: /START/i }).click();
  await expect(page).toHaveURL(/registrati\/.+piano=START/);
  await expect(page.locator("[data-selected-plan]")).toContainText("Start");
  await expect(page.locator("[data-selected-plan]")).toContainText("120");
  await expect(page.getByLabel("Email professionale", { exact: true })).toBeDisabled();
});

test("anteprime senza richieste API o sessioni", async ({ page }) => {
  const apiCalls: string[] = [];
  page.on("request", request => { if (["fetch", "xhr"].includes(request.resourceType())) apiCalls.push(request.url()); });
  for (const route of ["/accedi/", "/registrati/?piano=TOP", "/registrati/?piano=inesistente"]) {
    await page.goto(route);
    for (const input of await page.locator("input").all()) await expect(input).toBeDisabled();
    for (const button of await page.getByRole("button").all()) await expect(button).toBeDisabled();
  }
  expect(apiCalls).toEqual([]);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
  await expect(page.locator("[data-selected-plan]")).toContainText("Free");
});

test("pagine responsive e workspace esistente", async ({ page }) => {
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ["/", "/accedi/", "/registrati/"]) {
      await page.goto(route);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    }
    await page.goto("/");
    await page.screenshot({ path: `test-results/marketing/landing-${width}.png`, fullPage: true });
  }
  await page.goto("/workspace/");
  await expect(page.locator("main")).toBeVisible();
  await expect(page.getByRole("link", { name: /CTE/i }).first()).toBeVisible();
});
