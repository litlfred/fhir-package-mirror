#!/usr/bin/env bun
/**
 * Like folio-assistant-core's fetch-dspace-item.ts, but for an item with several
 * PDF bitstreams: names the one to take. It narrows the bitstream listing to that
 * file, then runs the same fetchItem(), so intake.json and the Dublin Core record
 * come out the same way.
 *
 *   bun run scripts/fetch-dspace-pdf.ts <handle URL> <pdf name> --out <dir>
 */
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { fetchItem } from "../../folio-assistant-core/scripts/fetch-dspace-item.ts";

const [url, pdfName, flag, out] = process.argv.slice(2);
if (!url || !pdfName || flag !== "--out" || !out) {
  console.error("usage: fetch-dspace-pdf.ts <handle URL> <pdf name> --out <dir>");
  process.exit(2);
}
const real = globalThis.fetch;
globalThis.fetch = (async (input: any, init?: any) => {
  const res = await real(input, init);
  if (!String(input).includes("/bitstreams") || !res.ok) return res;
  const body = await res.clone().json().catch(() => null);
  const list = body?._embedded?.bitstreams;
  if (!Array.isArray(list)) return res;
  const kept = list.filter((b: any) => !/\.pdf$/i.test(b.name) || b.name === pdfName);
  if (!kept.some((b: any) => b.name === pdfName)) throw new Error(`${pdfName} not among ${list.map((b: any) => b.name).join(", ")}`);
  body._embedded.bitstreams = kept;
  return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
}) as typeof fetch;

try {
  const f = await fetchItem(url);
  const dir = join(out, f.docId);
  if (existsSync(join(dir, "intake.json"))) throw new Error(`${dir}/intake.json exists`);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, f.pdfName), f.pdf);
  writeFileSync(join(dir, `${f.docId}.dc.json`), `${JSON.stringify(f.record, null, 2)}\n`);
  writeFileSync(join(dir, "intake.json"), `${JSON.stringify(f.intake, null, 2)}\n`);
  console.log(`${url} -> ${dir}/${f.pdfName} (${f.pdf.length} bytes)`);
  console.log(`  licence: ${f.intake.licence?.status} ${f.intake.licence?.id ?? ""}`);
} catch (err) {
  console.error(`✗ ${(err as Error).message}`);
  process.exit(1);
}
