import { spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { setTimeout as sleep } from "node:timers/promises";

export interface ServerOptions {
  /** Server port. If omitted, a free port is auto-picked. */
  port?: number;
  /** Server host (default: 127.0.0.1). */
  host?: string;
  /**
   * Skip spawning a new server and use this base URL instead.
   * When set, lifecycle.start() resolves immediately without booting `uvx`.
   */
  baseUrl?: string;
  /** Moorcheh API key passed to the server via env. */
  apiKey?: string;
  /**
   * Path to the `uvx` binary. Defaults to `uvx`, resolved via PATH.
   */
  uvxPath?: string;
  /**
   * Memanto package spec passed to uvx. Defaults to `memanto`.
   * Use e.g. `memanto==0.1.4` to pin a version.
   */
  packageSpec?: string;
  /** Max ms to wait for /health to return 200 (default: 60_000). */
  healthTimeoutMs?: number;
  /** If true, stream server stdout/stderr to the parent process. */
  verbose?: boolean;
}

export class ServerLifecycle {
  private process: ChildProcess | null = null;
  private url: string | null = null;
  private cleanupRegistered = false;

  constructor(private readonly opts: ServerOptions = {}) {}

  get baseUrl(): string {
    if (!this.url) {
      throw new Error("Server not started. Call start() first.");
    }
    return this.url;
  }

  async start(): Promise<string> {
    if (this.url) return this.url;

    if (this.opts.baseUrl) {
      this.url = this.opts.baseUrl.replace(/\/$/, "");
      return this.url;
    }

    const host = this.opts.host ?? "127.0.0.1";
    const port = this.opts.port ?? (await pickFreePort());
    const uvx = this.opts.uvxPath ?? "uvx";
    const spec = this.opts.packageSpec ?? "memanto";

    const args = [spec, "serve", "--host", host, "--port", String(port)];
    const env: NodeJS.ProcessEnv = { ...process.env };
    if (this.opts.apiKey) env.MOORCHEH_API_KEY = this.opts.apiKey;

    const child = spawn(uvx, args, {
      env,
      stdio: this.opts.verbose ? "inherit" : "ignore",
    });

    this.process = child;
    this.registerCleanup();

    const baseUrl = `http://${host}:${port}`;

    const spawnError = new Promise<never>((_, reject) => {
      child.on("error", (err: NodeJS.ErrnoException) => {
        if (err.code === "ENOENT") {
          reject(
            new Error(
              "Could not find `uvx`. Install uv from https://docs.astral.sh/uv/ and ensure it is on PATH.",
            ),
          );
        } else {
          reject(err);
        }
      });
    });

    await Promise.race([
      this.waitForHealth(baseUrl, this.opts.healthTimeoutMs ?? 60_000),
      spawnError,
    ]);
    this.url = baseUrl;
    return baseUrl;
  }

  async stop(): Promise<void> {
    const child = this.process;
    this.process = null;
    this.url = null;
    if (!child || child.killed) return;

    let exited = false;
    await new Promise<void>((resolve, reject) => {
      child.once("exit", () => { exited = true; resolve(); });
      child.kill("SIGTERM");
      setTimeout(() => {
        if (!exited) child.kill("SIGKILL");
      }, 5_000);
    });
  }

  private async waitForHealth(baseUrl: string, timeoutMs: number): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    let lastErr: unknown = null;
    while (Date.now() < deadline) {
      if (this.process && this.process.exitCode !== null) {
        throw new Error(
          `memanto server exited with code ${this.process.exitCode} before becoming healthy.`,
        );
      }
      try {
        const res = await fetch(`${baseUrl}/health`);
        if (res.ok) return;
      } catch (err) {
        lastErr = err;
      }
      await sleep(250);
    }
    await this.stop();
    throw new Error(
      `memanto server at ${baseUrl} did not become healthy within ${timeoutMs}ms${
        lastErr ? `: ${(lastErr as Error).message}` : ""
      }`,
    );
  }

  private registerCleanup(): void {
    if (this.cleanupRegistered) return;
    this.cleanupRegistered = true;
    const cleanup = () => {
      if (this.process && !this.process.killed) {
        this.process.kill("SIGTERM");
      }
    };
    process.once("exit", cleanup);
    process.once("SIGINT", () => {
      cleanup();
      process.exit(130);
    });
    process.once("SIGTERM", () => {
      cleanup();
      process.exit(143);
    });
  }
}

async function pickFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, () => {
      const addr = srv.address();
      if (typeof addr === "object" && addr) {
        const port = addr.port;
        srv.close(() => resolve(port));
      } else {
        srv.close(() => reject(new Error("Failed to pick free port")));
      }
    });
  });
}
