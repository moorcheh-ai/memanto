import { afterEach, describe, expect, it, vi } from "vitest";
import { EventEmitter } from "node:events";
import { createServer, type Server } from "node:http";
import { AddressInfo } from "node:net";
import { ServerLifecycle } from "../src/lifecycle.js";

const spawnMock = vi.hoisted(() => vi.fn());

vi.mock("node:child_process", async (importOriginal) => ({
  ...(await importOriginal<typeof import("node:child_process")>()),
  spawn: spawnMock,
}));

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

  it("coalesces concurrent starts into one server process", async () => {
    const child = Object.assign(new EventEmitter(), {
      exitCode: null,
      killed: false,
      kill: vi.fn(),
    });
    child.kill.mockImplementation(() => {
      child.killed = true;
      queueMicrotask(() => child.emit("exit", 0));
      return true;
    });
    spawnMock.mockReturnValue(child);
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({ ok: true } as Response);

    const life = new ServerLifecycle();
    const [first, second] = await Promise.all([life.start(), life.start()]);
    cleanupFns.push(() => life.stop());

    expect(first).toBe(second);
    expect(spawnMock).toHaveBeenCalledTimes(1);
    fetchSpy.mockRestore();
  });

  it("does not let a stale startup failure clear a newer promise", async () => {
    const life = new ServerLifecycle();
    let rejectStartup!: (reason: Error) => void;
    const stale = new Promise<string>((_, reject) => {
      rejectStartup = reject;
    });
    const internals = life as unknown as {
      startOnce: () => Promise<string>;
      starting: Promise<string> | null;
    };
    vi.spyOn(internals, "startOnce").mockReturnValue(stale);

    const first = life.start();
    const replacement = Promise.resolve("http://127.0.0.1:9000");
    internals.starting = replacement;
    rejectStartup(new Error("startup failed"));

    await expect(first).rejects.toThrow("startup failed");
    expect(internals.starting).toBe(replacement);
  });

  it("waits for an in-flight start before stopping its process", async () => {
    const child = Object.assign(new EventEmitter(), {
      exitCode: null,
      killed: false,
      kill: vi.fn(),
    });
    child.kill.mockImplementation(() => {
      child.killed = true;
      queueMicrotask(() => child.emit("exit", 0));
      return true;
    });
    spawnMock.mockReturnValue(child);
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({ ok: true } as Response);

    const life = new ServerLifecycle();
    const starting = life.start();
    await life.stop();
    await starting;

    expect(child.kill).toHaveBeenCalledTimes(1);
    expect(() => life.baseUrl).toThrow(/Server not started/);
    fetchSpy.mockRestore();
  });
});
