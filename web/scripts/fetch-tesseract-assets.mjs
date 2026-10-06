/**
 * Copy Tesseract worker/wasm into public/ and download English traineddata
 * so OCR works on a self-hosted server with no third-party CDN at runtime.
 */
import { createWriteStream, existsSync, mkdirSync, readdirSync, copyFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = join(root, "public", "tesseract");
mkdirSync(outDir, { recursive: true });

function copyMatching(fromDir, pattern) {
  if (!existsSync(fromDir)) {
    throw new Error(`Missing ${fromDir}. Run npm install inside web/ first.`);
  }
  let copied = 0;
  for (const name of readdirSync(fromDir)) {
    if (!pattern.test(name)) continue;
    const src = join(fromDir, name);
    if (!statSync(src).isFile()) continue;
    copyFileSync(src, join(outDir, name));
    copied += 1;
  }
  if (copied === 0) {
    throw new Error(`No files matched ${pattern} in ${fromDir}`);
  }
}

const tesseractPkg = join(root, "node_modules", "tesseract.js", "dist");
const corePkg = join(root, "node_modules", "tesseract.js-core");

copyMatching(tesseractPkg, /^worker\.min\.js$/);
// LSTM builds only. The .wasm.js files embed the binary, and the default
// worker uses the LSTM engine, so the legacy cores are unnecessary.
copyMatching(corePkg, /^tesseract-core(?:-relaxedsimd|-simd)?-lstm\.wasm\.js$/);

const trained = join(outDir, "eng.traineddata.gz");
if (!existsSync(trained) || statSync(trained).size < 1000) {
  const url = "https://tessdata.projectnaptha.com/4.0.0/eng.traineddata.gz";
  const response = await fetch(url);
  if (!response.ok || !response.body) {
    throw new Error(`Failed to download ${url}: ${response.status}`);
  }
  await pipeline(Readable.fromWeb(response.body), createWriteStream(trained));
}

console.log(`Tesseract assets ready in ${outDir}`);
