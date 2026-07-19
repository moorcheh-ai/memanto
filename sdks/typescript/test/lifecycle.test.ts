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
    const originalListenerCount = process.listenerCount.bind(process);
    const listenerCountSpy = vi
      .spyOn(process, "listenerCount")
      .mockImplementation((event) =>
        event === "SIGINT" ? 1 : originalListenerCount(event),
      );
    cleanupFns.push(() => {
      exitSpy.mockRestore();
      listenerCountSpy.mockRestore();
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
    process.exitCode = undefined;
    life.cleanupHandlers?.sigint();

    expect(exitSpy).not.toHaveBeenCalled();
    expect(process.exitCode).toBe(130);

    listenerCountSpy.mockImplementation((event) =>
      event === "SIGTERM" ? 0 : originalListenerCount(event),
    );
    process.exitCode = undefined;
    life.cleanupHandlers?.sigterm();

    expect(exitSpy).toHaveBeenCalledOnce();
    expect(process.exitCode).toBe(143);
  });

  it("clears the force-kill timer when the child exits", async () => {
    vi.useFakeTimers();
    cleanupFns.push(() => vi.useRealTimers());
    const child = Object.assign(new EventEmitter(), {
      killed: false,
      exitCode: null,
      signalCode: null,
      kill: vi.fn(() => true),
    }) as unknown as ChildProcess;
    const life = new ServerLifecycle() as unknown as {
      process: ChildProcess | null;
      url: string | null;
      stop(): Promise<void>;
    };
    life.process = child;
    life.url = "http://127.0.0.1:9999";

    const stopped = life.stop();
    child.emit("exit", 0, null);
    await stopped;

    expect(vi.getTimerCount()).toBe(0);
  });

  it("settles shutdown when the child emits an error", async () => {
    vi.useFakeTimers();
    cleanupFns.push(() => vi.useRealTimers());
    const child = Object.assign(new EventEmitter(), {
      killed: false,
      exitCode: null,
      signalCode: null,
      kill: vi.fn(() => true),
    }) as unknown as ChildProcess;
    const life = new ServerLifecycle() as unknown as {
      process: ChildProcess | null;
      stop(): Promise<void>;
    };
    life.process = child;

    const stopped = life.stop();
    child.emit("error", new Error("signal delivery failed"));

    await expect(stopped).resolves.toBeUndefined();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("returns immediately when the child has already exited", async () => {
    const child = Object.assign(new EventEmitter(), {
      killed: false,
      exitCode: 0,
      signalCode: null,
      kill: vi.fn(() => true),
    }) as unknown as ChildProcess;
    const life = new ServerLifecycle() as unknown as {
      process: ChildProcess | null;
      stop(): Promise<void>;
    };
    life.process = child;

    await expect(life.stop()).resolves.toBeUndefined();
    expect(child.kill).not.toHaveBeenCalled();
  });

  it("waits for exit when a kill signal was sent but the child is still alive", async () => {
    const child = Object.assign(new EventEmitter(), {
      killed: true,
      exitCode: null,
      signalCode: null,
      kill: vi.fn(() => true),
    }) as unknown as ChildProcess;
    const life = new ServerLifecycle() as unknown as {
      process: ChildProcess | null;
      stop(): Promise<void>;
    };
    life.process = child;

    const stopped = life.stop();
    expect(child.kill).toHaveBeenCalledWith("SIGTERM");
    child.emit("exit", 0, null);

    await expect(stopped).resolves.toBeUndefined();
  });

  it("rejects health polling after a concurrent stop", async () => {
    const life = new ServerLifecycle() as unknown as {
      waitForHealth(baseUrl: string, timeoutMs: number): Promise<void>;
    };

    await expect(
      life.waitForHealth("http://127.0.0.1:9999", 100),
    ).rejects.toThrow(/stopped before becoming healthy/);
  });

  it("fails health polling immediately after signal termination", async () => {
    const child = Object.assign(new EventEmitter(), {
      killed: true,
      exitCode: null,
      signalCode: "SIGKILL",
      kill: vi.fn(() => true),
    }) as unknown as ChildProcess;
    const life = new ServerLifecycle() as unknown as {
      process: ChildProcess | null;
      waitForHealth(baseUrl: string, timeoutMs: number): Promise<void>;
    };
    life.process = child;

    await expect(
      life.waitForHealth("http://127.0.0.1:9999", 100),
    ).rejects.toThrow(/signal: SIGKILL/);
  });

  it("does not let an old health poll observe a replacement child", async () => {
    const originalChild = Object.assign(new EventEmitter(), {
      killed: false,
      exitCode: null,
      signalCode: null,
      kill: vi.fn(() => true),
    }) as unknown as ChildProcess;
    const replacementChild = Object.assign(new EventEmitter(), {
      killed: false,
      exitCode: null,
      signalCode: null,
      kill: vi.fn(() => true),
    }) as unknown as ChildProcess;
    const life = new ServerLifecycle() as unknown as {
      process: ChildProcess | null;
      waitForHealth(baseUrl: string, timeoutMs: number): Promise<void>;
    };
    life.process = originalChild;
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      life.process = replacementChild;
      return new Response(null, { status: 503 });
    });
    cleanupFns.push(() => fetchSpy.mockRestore());

    await expect(
      life.waitForHealth("http://127.0.0.1:9999", 100),
    ).rejects.toThrow(/stopped before becoming healthy/);
    expect(replacementChild.kill).not.toHaveBeenCalled();
  });

  it("bounds each health request by the configured deadline", async () => {
    const child = Object.assign(new EventEmitter(), {
      killed: false,
      exitCode: null,
      signalCode: null,
      kill: vi.fn(() => true),
    }) as unknown as ChildProcess;
    const life = new ServerLifecycle() as unknown as {
      process: ChildProcess | null;
      stop(): Promise<void>;
      waitForHealth(baseUrl: string, timeoutMs: number): Promise<void>;
    };
    life.process = child;
    const stopSpy = vi.spyOn(life, "stop").mockResolvedValue();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => reject(signal.reason), {
            once: true,
          });
        }),
    );
    cleanupFns.push(() => {
      fetchSpy.mockRestore();
      stopSpy.mockRestore();
    });

    await expect(
      life.waitForHealth("http://127.0.0.1:9999", 30),
    ).rejects.toThrow(/did not become healthy within 30ms/);
    expect(fetchSpy.mock.calls[0]?.[1]?.signal).toBeInstanceOf(AbortSignal);
    expect(stopSpy).toHaveBeenCalledOnce();
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
