#!/usr/bin/env node
// Fetch the latest OpenAPI spec from a running memanto server and write it
// to ./openapi.json so codegen runs against the committed baseline.
//
// Usage:
//   node scripts/fetch-openapi.mjs [--url http://localhost:8000]
//   MEMANTO_OPENAPI_URL=... node scripts/fetch-openapi.mjs

import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

const argUrl = process.argv.find((a) => a.startsWith("--url="));
const url =
  (argUrl && argUrl.slice("--url=".length)) ||
  process.env.MEMANTO_OPENAPI_URL ||
  "http://localhost:8000/openapi.json";

const out = resolve(process.cwd(), "openapi.json");

try {
  const res = await fetch(url);
  if (!res.ok) {
    console.error(`Failed to fetch ${url}: HTTP ${res.status}`);
    process.exit(1);
  }
  const spec = await res.json();
  writeFileSync(out, JSON.stringify(spec, null, 2) + "\n");
  console.log(`Wrote ${out}`);
} catch (err) {
  console.error(`Failed to fetch OpenAPI from ${url}: ${err.message}`);
  console.error("Hint: start the server with `uvx memanto serve` first.");
  process.exit(1);
}
