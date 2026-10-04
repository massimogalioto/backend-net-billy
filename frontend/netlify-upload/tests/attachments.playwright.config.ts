import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";
export default defineConfig({
  testDir: ".", testMatch: "attachments.spec.ts",
  use: { baseURL: "http://127.0.0.1:4173" },
  outputDir: "../../test-results/attachments",
  webServer: { command: "node scripts/serve-static.mjs", cwd: resolve(__dirname, "../.."), url: "http://127.0.0.1:4173", reuseExistingServer: false },
});
