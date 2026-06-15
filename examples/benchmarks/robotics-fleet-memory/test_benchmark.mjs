import assert from "node:assert/strict";
import test from "node:test";

import {
  loadDataset,
  renderMarkdown,
  runBenchmark,
  scoreContext,
  tokenCount,
} from "./run_benchmark.mjs";

test("dataset includes source events and golden queries", () => {
  const dataset = loadDataset();

  assert.equal(dataset.events.length, 12);
  assert.equal(dataset.queries.length, 7);
  assert.ok(dataset.events.some((event) => event.sensitive));
});

test("token counting is stable for benchmark summaries", () => {
  assert.equal(tokenCount("Robot R-17 goes to Dock 4."), 6);
  assert.equal(tokenCount(""), 0);
});

test("scoring rejects stale facts and prohibited credentials", () => {
  const query = {
    expected_terms: ["Dock 4"],
    stale_terms: ["aisle A"],
    prohibited_terms: ["TEMP-SECRET-7781"],
  };

  const score = scoreContext(
    query,
    "R-17 should use Dock 4. Old note: aisle A. TEMP-SECRET-7781.",
  );

  assert.equal(score.accurate, false);
  assert.deepEqual(score.staleHits, ["aisle A"]);
  assert.deepEqual(score.prohibitedHits, ["TEMP-SECRET-7781"]);
});

test("active digest beats passive baselines on accuracy and safety", () => {
  const results = runBenchmark({ iterations: 5 });
  const byName = Object.fromEntries(
    results.metrics.map((metric) => [metric.backend, metric]),
  );

  assert.equal(byName.active_fleet_digest.retrievalAccuracy, 1);
  assert.equal(byName.active_fleet_digest.secretLeakRate, 0);
  assert.ok(
    byName.active_fleet_digest.retrievalAccuracy >
      byName.append_only_log.retrievalAccuracy,
  );
  assert.ok(
    byName.active_fleet_digest.totalRetrievedTokens <
      byName.append_only_log.totalRetrievedTokens,
  );
  assert.ok(
    byName.active_fleet_digest.staleConflictRate <
      byName.append_only_log.staleConflictRate,
  );
});

test("markdown renderer includes the metric table", () => {
  const markdown = renderMarkdown(runBenchmark({ iterations: 1 }));

  assert.match(markdown, /Robotics Fleet Memory Benchmark Results/);
  assert.match(markdown, /active_fleet_digest/);
  assert.match(markdown, /Secret leak rate/);
});
