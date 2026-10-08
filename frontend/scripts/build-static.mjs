import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const stage = resolve(root, ".static-build");
const output = resolve(root, "netlify-upload");
// Only generated directories with fixed paths inside frontend are removed.
for (const target of [stage, output]) {
  if (dirname(target) !== root) throw new Error("Invalid build directory");
}
rmSync(stage, { recursive: true, force: true });
mkdirSync(stage, { recursive: true });
for (const name of ["app", "components", "lib", "public", "CaricamentoMassivoCTE.tsx", "cte-batch.ts", "tsconfig.json", "next-env.d.ts", "package.json"]) {
  cpSync(resolve(root, name), resolve(stage, name), { recursive: true,
    filter: source => source !== resolve(root, "app", "api") });
}
writeFileSync(resolve(stage, "next.config.ts"), 'export default { output: "export", trailingSlash: true, images: { unoptimized: true }, poweredByHeader: false };\n');
const build = spawnSync(process.execPath, [resolve(root, "node_modules/next/dist/bin/next"), "build", stage, "--webpack"], {
  cwd: root, stdio: "inherit", env: { ...process.env, NEXT_PUBLIC_STATIC_MODE: "true" },
});
if (build.status !== 0) process.exit(build.status ?? 1);
if (!existsSync(resolve(stage, "out/index.html"))) throw new Error("Static export missing");
rmSync(output, { recursive: true, force: true });
cpSync(resolve(stage, "out"), output, { recursive: true });
writeFileSync(resolve(output, "_headers"), "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n");
const verification = spawnSync(process.execPath, [resolve(root, "scripts/verify-static-assets.mjs"), output], { stdio: "inherit" });
if (verification.status !== 0) process.exit(verification.status ?? 1);
console.log(`Cartella pronta per Netlify: ${output}`);
