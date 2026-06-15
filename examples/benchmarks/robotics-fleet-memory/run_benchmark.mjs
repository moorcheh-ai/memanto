import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEFAULT_DATASET = path.join(
  __dirname,
  "dataset",
  "robotics_fleet_sessions.json",
);

const STOP_WORDS = new Set([
  "after",
  "and",
  "api",
  "are",
  "audits",
  "for",
  "from",
  "how",
  "into",
  "memory",
  "now",
  "still",
  "the",
  "this",
  "to",
  "what",
  "where",
  "who",
  "with",
]);

function normalize(value) {
  return String(value)
    .toLowerCase()
    .replace(/[^a-z0-9%.:-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tokenCount(value) {
  const normalized = normalize(value);
  return normalized === "" ? 0 : normalized.split(" ").length;
}

function keywords(value) {
  return normalize(value)
    .split(" ")
    .filter((token) => token.length > 2 && !STOP_WORDS.has(token));
}

function overlapScore(text, query) {
  const textSet = new Set(keywords(text));
  return keywords(query).filter((token) => textSet.has(token)).length;
}

function percentile(values, percentileRank) {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.ceil((percentileRank / 100) * sorted.length) - 1;
  return sorted[Math.max(0, Math.min(index, sorted.length - 1))];
}

function rounded(value, digits = 3) {
  return Number(value.toFixed(digits));
}

function loadDataset(datasetPath = DEFAULT_DATASET) {
  return JSON.parse(fs.readFileSync(datasetPath, "utf8"));
}

function relatedEvents(events, question, options = {}) {
  const scored = events
    .map((event, index) => ({
      event,
      index,
      score: overlapScore(event.text, question),
    }))
    .filter((item) => item.score > 0)
    .sort((left, right) => left.index - right.index);

  if (scored.length === 0 && options.fallbackToRecent) {
    return events.slice(-options.fallbackToRecent);
  }

  const selected = options.limit ? scored.slice(-options.limit) : scored;
  return selected.map((item) => item.event);
}

class AppendOnlyLogBackend {
  constructor() {
    this.name = "append_only_log";
    this.description = "Passive baseline that keeps every matching shift note.";
    this.events = [];
    this.ingestedTokens = 0;
  }

  ingest(event) {
    this.events.push(event);
    this.ingestedTokens += tokenCount(event.text);
  }

  retrieve(query) {
    return relatedEvents(this.events, query.question, { fallbackToRecent: 3 })
      .map((event) => `[${event.id}] ${event.text}`)
      .join("\n");
  }
}

class RecentWindowBackend {
  constructor(windowSize = 5) {
    this.name = "recent_window";
    this.description = "Low-token recency baseline that forgets older durable facts.";
    this.events = [];
    this.ingestedTokens = 0;
    this.windowSize = windowSize;
  }

  ingest(event) {
    this.events.push(event);
    this.ingestedTokens += tokenCount(event.text);
  }

  retrieve(query) {
    const window = this.events.slice(-this.windowSize);
    return relatedEvents(window, query.question, { fallbackToRecent: 2 })
      .map((event) => `[${event.id}] ${event.text}`)
      .join("\n");
  }
}

class ActiveFleetDigestBackend {
  constructor() {
    this.name = "active_fleet_digest";
    this.description =
      "Memanto-style active memory digest with overwrite semantics.";
    this.facts = new Map();
    this.ingestedTokens = 0;
    this.sensitiveSuppressed = 0;
  }

  ingest(event) {
    this.ingestedTokens += tokenCount(event.text);

    if (event.sensitive) {
      this.sensitiveSuppressed += 1;
      return;
    }

    for (const update of event.updates ?? []) {
      const key = `${update.entity}:${update.field}`;
      this.facts.set(key, {
        label: update.label,
        value: update.value,
      });
    }
  }

  retrieve(query) {
    const digestLines = [...this.facts.values()].map(
      (fact) => `${fact.label}: ${fact.value}.`,
    );

    if (this.sensitiveSuppressed > 0) {
      digestLines.push(
        "Sensitive credentials suppressed from long-term memory.",
      );
    }

    const queryKeywords = new Set(keywords(query.question));
    const matches = digestLines.filter((line) => {
      const lineKeywords = new Set(keywords(line));
      if (
        queryKeywords.has("token") ||
        queryKeywords.has("vendor") ||
        queryKeywords.has("credential")
      ) {
        return normalize(line).includes("sensitive credentials suppressed");
      }
      return [...queryKeywords].some((token) => lineKeywords.has(token));
    });

    return (matches.length > 0 ? matches : digestLines).join("\n");
  }
}

const BACKENDS = [
  () => new AppendOnlyLogBackend(),
  () => new RecentWindowBackend(),
  () => new ActiveFleetDigestBackend(),
];

function termHits(context, terms) {
  const normalizedContext = normalize(context);
  return terms.filter((term) => normalizedContext.includes(normalize(term)));
}

function scoreContext(query, context) {
  const expectedHits = termHits(context, query.expected_terms);
  const missingExpected = query.expected_terms.filter(
    (term) => !expectedHits.includes(term),
  );
  const staleHits = termHits(context, query.stale_terms);
  const prohibitedHits = termHits(context, query.prohibited_terms);

  return {
    accurate:
      missingExpected.length === 0 &&
      staleHits.length === 0 &&
      prohibitedHits.length === 0,
    expectedHits,
    missingExpected,
    staleHits,
    prohibitedHits,
    retrievedTokens: tokenCount(context),
  };
}

function runBackend(factory, dataset, iterations) {
  const backend = factory();
  for (const event of dataset.events) {
    backend.ingest(event);
  }

  const queryResults = [];
  const latenciesMs = [];

  for (const query of dataset.queries) {
    let context = "";
    for (let round = 0; round < iterations; round += 1) {
      const start = process.hrtime.bigint();
      context = backend.retrieve(query);
      const end = process.hrtime.bigint();
      latenciesMs.push(Number(end - start) / 1_000_000);
    }

    const score = scoreContext(query, context);
    queryResults.push({
      id: query.id,
      accurate: score.accurate,
      retrievedTokens: score.retrievedTokens,
      missingExpected: score.missingExpected,
      staleHits: score.staleHits,
      prohibitedHits: score.prohibitedHits,
    });
  }

  const accurateCount = queryResults.filter((result) => result.accurate).length;
  const staleCount = queryResults.filter(
    (result) => result.staleHits.length > 0,
  ).length;
  const leakCount = queryResults.filter(
    (result) => result.prohibitedHits.length > 0,
  ).length;
  const retrievedTokens = queryResults.reduce(
    (total, result) => total + result.retrievedTokens,
    0,
  );

  return {
    backend: backend.name,
    description: backend.description,
    queryCount: dataset.queries.length,
    totalIngestedTokens: backend.ingestedTokens,
    totalRetrievedTokens: retrievedTokens,
    avgRetrievedTokens: rounded(retrievedTokens / dataset.queries.length, 2),
    retrievalAccuracy: rounded(accurateCount / dataset.queries.length, 3),
    staleConflictRate: rounded(staleCount / dataset.queries.length, 3),
    secretLeakRate: rounded(leakCount / dataset.queries.length, 3),
    p95LatencyMs: rounded(percentile(latenciesMs, 95), 4),
    queryResults,
  };
}

function runBenchmark(options = {}) {
  const dataset = loadDataset(options.datasetPath);
  const iterations =
    options.iterations ?? Number(process.env.BENCHMARK_ITERATIONS ?? 50);
  const backends = BACKENDS.map((factory) =>
    runBackend(factory, dataset, iterations),
  );

  return {
    benchmark: dataset.name,
    datasetVersion: dataset.version,
    generatedAt: new Date().toISOString(),
    iterationsPerQuery: iterations,
    eventCount: dataset.events.length,
    queryCount: dataset.queries.length,
    metrics: backends,
  };
}

function renderMarkdown(results) {
  const lines = [
    "# Robotics Fleet Memory Benchmark Results",
    "",
    `Dataset: ${results.benchmark} (${results.datasetVersion})`,
    `Events: ${results.eventCount}`,
    `Queries: ${results.queryCount}`,
    `Iterations per query: ${results.iterationsPerQuery}`,
    "",
    "| Backend | Accuracy | Retrieved tokens | Avg retrieved tokens | Stale conflict rate | Secret leak rate | p95 latency (ms) |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
  ];

  for (const metric of results.metrics) {
    lines.push(
      `| ${metric.backend} | ${metric.retrievalAccuracy} | ${metric.totalRetrievedTokens} | ${metric.avgRetrievedTokens} | ${metric.staleConflictRate} | ${metric.secretLeakRate} | ${metric.p95LatencyMs} |`,
    );
  }

  lines.push("", "## Per-query failures", "");
  for (const metric of results.metrics) {
    const failures = metric.queryResults.filter((result) => !result.accurate);
    lines.push(`### ${metric.backend}`);
    if (failures.length === 0) {
      lines.push("", "No failures.", "");
      continue;
    }
    for (const failure of failures) {
      const problems = [
        failure.missingExpected.length > 0
          ? `missing: ${failure.missingExpected.join(", ")}`
          : "",
        failure.staleHits.length > 0
          ? `stale: ${failure.staleHits.join(", ")}`
          : "",
        failure.prohibitedHits.length > 0
          ? `leak: ${failure.prohibitedHits.join(", ")}`
          : "",
      ].filter(Boolean);
      lines.push(`- ${failure.id}: ${problems.join("; ")}`);
    }
    lines.push("");
  }

  while (lines.at(-1) === "") {
    lines.pop();
  }

  return `${lines.join("\n")}\n`;
}

function parseArgs(argv) {
  const args = {
    datasetPath: DEFAULT_DATASET,
    outputPath: null,
    markdownPath: null,
    iterations: undefined,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--dataset") {
      args.datasetPath = path.resolve(argv[index + 1]);
      index += 1;
    } else if (arg === "--output") {
      args.outputPath = path.resolve(argv[index + 1]);
      index += 1;
    } else if (arg === "--markdown") {
      args.markdownPath = path.resolve(argv[index + 1]);
      index += 1;
    } else if (arg === "--iterations") {
      args.iterations = Number(argv[index + 1]);
      index += 1;
    }
  }

  return args;
}

function writeFileEnsuringDirectory(filePath, content) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const results = runBenchmark(args);
  const markdown = renderMarkdown(results);

  if (args.outputPath) {
    writeFileEnsuringDirectory(
      args.outputPath,
      `${JSON.stringify(results, null, 2)}\n`,
    );
  }
  if (args.markdownPath) {
    writeFileEnsuringDirectory(args.markdownPath, markdown);
  }

  process.stdout.write(markdown);
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}

export {
  ActiveFleetDigestBackend,
  AppendOnlyLogBackend,
  RecentWindowBackend,
  loadDataset,
  renderMarkdown,
  runBenchmark,
  scoreContext,
  tokenCount,
};
