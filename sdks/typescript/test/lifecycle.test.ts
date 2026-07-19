import { afterEach, describe, expect, it, vi } from "vitest";
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

  it("removes process cleanup listeners when stopped", async () => {
    const eventNames = ["exit", "SIGINT", "SIGTERM"] as const;
    const before = Object.fromEntries(
      eventNames.map((event) => [event, process.listenerCount(event)]),
    );
    const life = new ServerLifecycle() as unknown as {
      registerCleanup(): void;
      stop(): Promise<void>;
    };
    cleanupFns.push(() => life.stop());

    life.registerCleanup();
    for (const event of eventNames) {
      expect(process.listenerCount(event)).toBe(before[event] + 1);
    }

    await life.stop();
    for (const event of eventNames) {
      expect(process.listenerCount(event)).toBe(before[event]);
    }
  });

  it("does not force the host process to exit on signals", async () => {
    const originalExitCode = process.exitCode;
    const exitSpy = vi
      .spyOn(process, "exit")
      .mockImplementation((() => undefined) as never);
    cleanupFns.push(() => {
      exitSpy.mockRestore();
      process.exitCode = originalExitCode;
    });
    const life = new ServerLifecycle() as unknown as {
      cleanupHandlers: {
        sigint: () => void;
        sigterm: () => void;
      } | null;
      registerCleanup(): void;
      stop(): Promise<void>;
    };
    cleanupFns.push(() => life.stop());

    life.registerCleanup();
    life.cleanupHandlers?.sigint();

    expect(exitSpy).not.toHaveBeenCalled();
    expect(process.exitCode).toBe(originalExitCode ?? 130);

    process.exitCode = undefined;
    life.cleanupHandlers?.sigterm();

    expect(exitSpy).not.toHaveBeenCalled();
    expect(process.exitCode).toBe(143);
  });

  it("stops health polling after the server process fails to spawn", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    cleanupFns.push(() => fetchSpy.mockRestore());
    const life = new ServerLifecycle({
      uvxPath: `missing-uvx-${Date.now()}`,
      healthTimeoutMs: 2_000,
    });
    cleanupFns.push(() => life.stop());

    await expect(life.start()).rejects.toThrow(/Could not find `uvx`/);
    const callsAfterFailure = fetchSpy.mock.calls.length;

    await new Promise((resolve) => setTimeout(resolve, 350));

    expect(fetchSpy).toHaveBeenCalledTimes(callsAfterFailure);
  });
});
