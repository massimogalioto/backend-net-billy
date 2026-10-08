import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

const output = resolve(process.argv[2] ?? "netlify-upload");
const htmlFiles = [];
function collect(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) collect(path);
    else if (entry.name.endsWith(".html")) htmlFiles.push(path);
  }
}
collect(output);
let checked = 0;
const missing = [];
for (const html of htmlFiles) {
  const content = readFileSync(html, "utf8");
  const references = content.matchAll(/(?:src|href)="(\/_next\/static\/[^"?]+)(?:\?[^"\s]*)?"/g);
  for (const match of references) {
    checked += 1;
    const asset = resolve(output, `.${match[1]}`);
    if (!existsSync(asset) || !statSync(asset).isFile()) missing.push(match[1]);
  }
}
if (!htmlFiles.some(file => file.endsWith("\\login\\index.html") || file.endsWith("/login/index.html"))) {
  missing.push("/login/index.html");
}
if (missing.length) throw new Error(`Static export has missing assets: ${[...new Set(missing)].join(", ")}`);
console.log(`Static asset verification passed: ${checked} HTML asset references across ${htmlFiles.length} pages.`);
