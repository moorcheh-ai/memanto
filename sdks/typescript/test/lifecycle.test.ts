import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChildProcess } from "node:child_process";
import { EventEmitter } from "node:events";
import { createServer, type Server } from "node:http";
import { AddressInfo } from "node:net";
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

  for (const stoppedState of [
    { name: "exitCode", exitCode: 1, signalCode: null },
    { name: "signalCode", exitCode: null, signalCode: "SIGTERM" },
  ] as const) {
    it(`does not hang when stopping an already exited child process with ${stoppedState.name}`, async () => {
      const life = new ServerLifecycle();
      const child = Object.assign(new EventEmitter(), {
        killed: false,
        exitCode: stoppedState.exitCode,
        signalCode: stoppedState.signalCode,
        kill: vi.fn(),
      }) as unknown as ChildProcess;

      (
        life as unknown as { process: ChildProcess | null; url: string | null }
      ).process = child;
      (
        life as unknown as { process: ChildProcess | null; url: string | null }
      ).url = "http://127.0.0.1:8765";

      const result = await Promise.race([
        life.stop().then(() => "stopped"),
        new Promise((resolve) => setTimeout(() => resolve("timeout"), 50)),
      ]);

      expect(result).toBe("stopped");
      expect(child.kill).not.toHaveBeenCalled();
    });
  }

  it("reports signaled startup exits without waiting for health timeout", async () => {
    const life = new ServerLifecycle();
    const child = Object.assign(new EventEmitter(), {
      killed: false,
      exitCode: null,
      signalCode: "SIGTERM",
      kill: vi.fn(),
    }) as unknown as ChildProcess;

    (
      life as unknown as { process: ChildProcess | null; url: string | null }
    ).process = child;

    await expect(
      (
        life as unknown as {
          waitForHealth(baseUrl: string, timeoutMs: number): Promise<void>;
        }
      ).waitForHealth("http://127.0.0.1:8765", 1_000),
    ).rejects.toThrow(
      "memanto server exited with signal SIGTERM before becoming healthy.",
    );

    expect(child.kill).not.toHaveBeenCalled();
  });
});
