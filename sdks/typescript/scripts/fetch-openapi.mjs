#!/usr/bin/env node
// Regenerate ./openapi.json the same way CI's drift check does: run
// scripts/generate_openapi.py at the repo root via uv. This must match
// CI exactly (down to the pinned version fallback) or the openapi-drift
// check will fail on every PR regardless of what actually changed.
//
// Usage:
//   node scripts/fetch-openapi.mjs

import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..", "..");
const out = resolve(process.cwd(), "openapi.json");

const result = spawnSync(
  "uv",
  ["run", "python", "scripts/generate_openapi.py"],
  { cwd: repoRoot, encoding: "utf-8" },
);

if (result.error) {
  console.error(`Failed to run uv: ${result.error.message}`);
  console.error("Hint: install uv (https://docs.astral.sh/uv/) and run `uv sync --all-extras --dev` first.");
  process.exit(1);
}

if (result.status !== 0) {
  console.error(result.stderr);
  process.exit(result.status ?? 1);
}

writeFileSync(out, result.stdout);
console.log(`Wrote ${out}`);
