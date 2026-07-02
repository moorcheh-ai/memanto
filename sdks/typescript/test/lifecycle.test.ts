import { afterEach, describe, expect, it, vi } from "vitest";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer, type Server } from "node:http";
import { AddressInfo } from "node:net";
import { setTimeout as sleep } from "node:timers/promises";
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

  it("stop resolves when the spawned process has already exited", async () => {
    const child = spawn(process.execPath, ["-e", "process.exit(0)"], {
      stdio: "ignore",
    });
    await new Promise<void>((resolve) => child.once("exit", () => resolve()));

    const life = new ServerLifecycle();
    const internals = life as unknown as {
      process: ChildProcess | null;
      url: string | null;
    };
    internals.process = child;
    internals.url = "http://127.0.0.1:1";

    const result = await Promise.race([
      life.stop().then(() => "stopped"),
      sleep(200).then(() => "timed-out"),
    ]);

    expect(result).toBe("stopped");
  });
});
