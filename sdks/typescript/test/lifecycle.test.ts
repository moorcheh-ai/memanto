import { afterEach, describe, expect, it, vi } from "vitest";
import { createServer, type Server } from "node:http";
import { AddressInfo } from "node:net";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ServerLifecycle } from "../src/lifecycle.js";

function startFakeHealthyServer(): Promise<{ url: string; close: () => void }> {
  return new Promise((resolve) => {
    const srv: Server = createServer((req, res) => {
      if (req.url === "/health") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: "ok" }));
      } else {
        res.writeHead(404);
        res.end();
      }
    });
    srv.listen(0, "127.0.0.1", () => {
      const addr = srv.address() as AddressInfo;
      resolve({
        url: `http://127.0.0.1:${addr.port}`,
        close: () => srv.close(),
      });
    });
  });
}

function pickFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const port = (srv.address() as AddressInfo).port;
      srv.close(() => resolve(port));
    });
  });
}

describe("ServerLifecycle", () => {
  let cleanupFns: Array<() => void | Promise<void>> = [];

  afterEach(async () => {
    for (const fn of cleanupFns) await fn();
    cleanupFns = [];
  });

  it("uses baseUrl without spawning when provided", async () => {
    const fake = await startFakeHealthyServer();
    cleanupFns.push(fake.close);

    const life = new ServerLifecycle({ baseUrl: fake.url });
    const url = await life.start();

    expect(url).toBe(fake.url);
    expect(life.baseUrl).toBe(fake.url);
  });

  it("strips trailing slash from baseUrl", async () => {
    const life = new ServerLifecycle({ baseUrl: "http://example.test/" });
    const url = await life.start();
    expect(url).toBe("http://example.test");
  });

  it("throws when baseUrl is read before start()", () => {
    const life = new ServerLifecycle({ baseUrl: "http://example.test" });
    expect(() => life.baseUrl).toThrow(/Server not started/);
  });

  it("polls /health and resolves once the server is up", async () => {
    const fake = await startFakeHealthyServer();
    cleanupFns.push(fake.close);

    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const life = new ServerLifecycle({ baseUrl: fake.url });
    await life.start();

    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("shares one local server start across concurrent callers", async () => {
    const dir = await mkdtemp(join(tmpdir(), "memanto-lifecycle-"));
    cleanupFns.push(() => rm(dir, { recursive: true, force: true }));
    const marker = join(dir, "starts.log");
    const serverScript = join(dir, "fake-uvx.mjs");
    await writeFile(
      serverScript,
      `
import { appendFileSync } from "node:fs";
import { createServer } from "node:http";

const port = Number(process.argv[process.argv.indexOf("--port") + 1]);
const host = process.argv[process.argv.indexOf("--host") + 1];
appendFileSync(${JSON.stringify(marker)}, "start\\n");
createServer((req, res) => {
  res.writeHead(req.url === "/health" ? 200 : 404);
  res.end();
}).listen(port, host);
`,
    );
    const port = await pickFreePort();
    const life = new ServerLifecycle({
      host: "127.0.0.1",
      port,
      uvxPath: process.execPath,
      packageSpec: serverScript,
      healthTimeoutMs: 5_000,
    });
    cleanupFns.push(() => life.stop());

    const [first, second] = await Promise.all([life.start(), life.start()]);

    expect(first).toBe(`http://127.0.0.1:${port}`);
    expect(second).toBe(first);
    expect((await readFile(marker, "utf8")).trim().split("\n")).toHaveLength(1);
  });
});
