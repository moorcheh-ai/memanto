import { afterEach, describe, expect, it } from "vitest";
import { createServer, type Server, type IncomingMessage } from "node:http";
import { AddressInfo } from "node:net";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { Memanto } from "../src/index.js";

interface Recorded {
  method: string;
  url: string;
  headers: NodeJS.Dict<string | string[]>;
  body: string;
}

function startFakeApi(
  agentId = "test-agent",
  opts: {
    requiredApiKey?: string;
    expireFirstSession?: boolean;
    expireFirstUpload?: boolean;
    rejectAllSessions?: boolean;
    coordinateConcurrentExpiration?: boolean;
  } = {},
): Promise<{
  url: string;
  recorded: Recorded[];
  close: () => void;
}> {
  const encodedAgentId = encodeURIComponent(agentId);
  return new Promise((resolve) => {
    const recorded: Recorded[] = [];
    let activationCount = 0;
    let expiredRememberCount = 0;
    let pendingRefreshReply: (() => void) | null = null;
    const srv: Server = createServer((req, res) => {
      collectBody(req).then((body) => {
        recorded.push({
          method: req.method ?? "",
          url: req.url ?? "",
          headers: req.headers,
          body,
        });

        const url = req.url ?? "";
        const reply = (status: number, payload: unknown) => {
          res.writeHead(status, { "Content-Type": "application/json" });
          res.end(JSON.stringify(payload));
        };

        if (url === "/health") return reply(200, { status: "ok" });
        const agentUrl = `/api/v2/agents/${encodedAgentId}`;
        const isManagementRequest =
          url === "/api/v2/status" ||
          url === "/api/v2/agents" ||
          (url === agentUrl && ["GET", "DELETE"].includes(req.method ?? "")) ||
          url === `${agentUrl}/activate`;
        if (
          opts.requiredApiKey &&
          isManagementRequest &&
          req.headers["x-api-key"] !== opts.requiredApiKey
        ) {
          return reply(401, { detail: "invalid API key" });
        }
        if (url === "/api/v2/status" && req.method === "GET")
          return reply(200, {
            session_id: "existing-session",
            agent_id: "existing-agent",
            namespace: "memanto_agent_existing_agent",
            started_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 3600_000).toISOString(),
            status: "active",
            pattern: "default",
            time_remaining_seconds: 3600,
          });
        if (url.startsWith(`/api/v2/agents/${encodedAgentId}/activate`)) {
          activationCount += 1;
          const sendActivation = () =>
            reply(200, {
              session_token:
                activationCount === 1 ? "fake-token" : "refreshed-token",
              agent_id: agentId,
              session_id: "sess-1",
              namespace: "memanto_agent_test_agent",
              started_at: new Date().toISOString(),
              expires_at: new Date(Date.now() + 3600_000).toISOString(),
              status: "active",
              pattern: "default",
            });
          if (
            opts.coordinateConcurrentExpiration &&
            activationCount === 2 &&
            expiredRememberCount < 2
          ) {
            pendingRefreshReply = sendActivation;
            return;
          }
          return sendActivation();
        }
        if (url === `/api/v2/agents/${encodedAgentId}` && req.method === "GET")
          return reply(404, { detail: "not found" });
        if (url === "/api/v2/agents" && req.method === "POST")
          return reply(201, { agent_id: agentId });
        if (
          url === `/api/v2/agents/${encodedAgentId}` &&
          req.method === "DELETE"
        )
          return reply(200, { agent_id: agentId, deleted: true });
        if (
          (opts.rejectAllSessions || opts.expireFirstSession) &&
          url === `/api/v2/agents/${encodedAgentId}/remember` &&
          (opts.rejectAllSessions ||
            req.headers["x-session-token"] === "fake-token")
        ) {
          expiredRememberCount += 1;
          reply(401, { detail: "Session token expired" });
          if (expiredRememberCount === 2 && pendingRefreshReply) {
            const releaseRefresh = pendingRefreshReply;
            pendingRefreshReply = null;
            releaseRefresh();
          }
          return;
        }
        if (url === `/api/v2/agents/${encodedAgentId}/remember`)
          return reply(200, {
            memory_id: "mem-1",
            agent_id: agentId,
            session_id: "sess-1",
            namespace: "memanto_agent_test_agent",
            status: "queued",
            provenance: "explicit_statement",
            confidence: 0.9,
            type: "fact",
          });
        if (url === `/api/v2/agents/${encodedAgentId}/recall`)
          return reply(200, {
            agent_id: agentId,
            session_id: "sess-1",
            query: "anything",
            memories: [],
            count: 0,
          });
        if (
          url === `/api/v2/agents/${encodedAgentId}/upload-file` &&
          req.method === "POST"
        ) {
          if (
            opts.expireFirstUpload &&
            req.headers["x-session-token"] === "fake-token"
          ) {
            return reply(401, { detail: "Session token expired" });
          }
          return reply(200, {
            agent_id: agentId,
            session_id: "sess-1",
            status: "queued",
            file_name: "notes.txt",
          });
        }
        return reply(404, { detail: "unknown route" });
      });
    });

    srv.listen(0, "127.0.0.1", () => {
      const addr = srv.address() as AddressInfo;
      resolve({
        url: `http://127.0.0.1:${addr.port}`,
        recorded,
        close: () => srv.close(),
      });
    });
  });
}

function collectBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    let s = "";
    req.on("data", (c) => (s += c.toString()));
    req.on("end", () => resolve(s));
  });
}

describe("Memanto", () => {
  let cleanupFns: Array<() => void | Promise<void>> = [];
  afterEach(async () => {
    for (const fn of cleanupFns) await fn();
    cleanupFns = [];
  });

  it("bootstraps and remembers", async () => {
    const api = await startFakeApi();
    cleanupFns.push(api.close);

    const m = new Memanto({ agentId: "test-agent", baseUrl: api.url });
    cleanupFns.push(() => m.close());

    const res = await m.remember({ content: "Het likes coffee" });
    expect(res).toMatchObject({ memory_id: "mem-1", status: "queued" });

    const remember = api.recorded.find((r) => r.url.endsWith("/remember"));
    expect(remember?.headers["x-session-token"]).toBe("fake-token");
  });

  it("recalls with session token", async () => {
    const api = await startFakeApi();
    cleanupFns.push(api.close);

    const m = new Memanto({ agentId: "test-agent", baseUrl: api.url });
    cleanupFns.push(() => m.close());

    const res = await m.recall({ query: "coffee" });
    expect(res).toMatchObject({ count: 0 });
  });

  it("authenticates remote management requests with apiKey", async () => {
    const apiKey = "mch_remote_test_key";
    const api = await startFakeApi("test-agent", { requiredApiKey: apiKey });
    cleanupFns.push(api.close);

    const m = new Memanto({ agentId: "test-agent", baseUrl: api.url, apiKey });
    cleanupFns.push(() => m.close());

    await m.remember({ content: "Remote servers require management auth" });
    await m.status();

    const managementRequests = api.recorded.filter((r) =>
      [
        "/api/v2/agents/test-agent",
        "/api/v2/agents",
        "/api/v2/agents/test-agent/activate",
        "/api/v2/status",
      ].includes(r.url),
    );
    expect(managementRequests).toHaveLength(4);
    expect(
      managementRequests.every((r) => r.headers["x-api-key"] === apiKey),
    ).toBe(true);

    const remember = api.recorded.find((r) => r.url.endsWith("/remember"));
    expect(remember?.headers["x-session-token"]).toBe("fake-token");
    expect(remember?.headers["x-api-key"]).toBeUndefined();
  });

  it("reactivates once and retries when the cached session expires", async () => {
    const api = await startFakeApi("test-agent", { expireFirstSession: true });
    cleanupFns.push(api.close);

    const m = new Memanto({ agentId: "test-agent", baseUrl: api.url });
    cleanupFns.push(() => m.close());

    const res = await m.remember({ content: "Het likes coffee" });

    expect(res).toMatchObject({ memory_id: "mem-1", status: "queued" });
    const activations = api.recorded.filter((r) => r.url.endsWith("/activate"));
    const agentLookups = api.recorded.filter(
      (r) => r.method === "GET" && r.url === "/api/v2/agents/test-agent",
    );
    const remembers = api.recorded.filter((r) => r.url.endsWith("/remember"));
    expect(activations).toHaveLength(2);
    expect(agentLookups).toHaveLength(1);
    expect(remembers).toHaveLength(2);
    expect(remembers[0]?.headers["x-session-token"]).toBe("fake-token");
    expect(remembers[1]?.headers["x-session-token"]).toBe("refreshed-token");
  });

  it("returns a second session failure without retrying again", async () => {
    const api = await startFakeApi("test-agent", { rejectAllSessions: true });
    cleanupFns.push(api.close);

    const m = new Memanto({ agentId: "test-agent", baseUrl: api.url });
    cleanupFns.push(() => m.close());

    await expect(m.remember({ content: "Het likes coffee" })).rejects.toThrow(
      /401/,
    );

    const activations = api.recorded.filter((r) => r.url.endsWith("/activate"));
    const remembers = api.recorded.filter((r) => r.url.endsWith("/remember"));
    expect(activations).toHaveLength(2);
    expect(remembers).toHaveLength(2);
    expect(remembers[0]?.headers["x-session-token"]).toBe("fake-token");
    expect(remembers[1]?.headers["x-session-token"]).toBe("refreshed-token");
  });

  it("shares one reactivation across concurrent expired-session retries", async () => {
    const api = await startFakeApi("test-agent", {
      expireFirstSession: true,
      coordinateConcurrentExpiration: true,
    });
    cleanupFns.push(api.close);

    const m = new Memanto({ agentId: "test-agent", baseUrl: api.url });
    cleanupFns.push(() => m.close());

    const results = await Promise.all([
      m.remember({ content: "Het likes coffee" }),
      m.remember({ content: "Het likes tea" }),
    ]);

    expect(results).toHaveLength(2);
    const activations = api.recorded.filter((r) => r.url.endsWith("/activate"));
    const remembers = api.recorded.filter((r) => r.url.endsWith("/remember"));
    expect(activations).toHaveLength(2);
    expect(
      remembers.filter((r) => r.headers["x-session-token"] === "fake-token"),
    ).toHaveLength(2);
    expect(
      remembers.filter(
        (r) => r.headers["x-session-token"] === "refreshed-token",
      ),
    ).toHaveLength(2);
  });

  it("rebootstraps after deleting the active agent", async () => {
    const api = await startFakeApi();
    cleanupFns.push(api.close);

    const m = new Memanto({ agentId: "test-agent", baseUrl: api.url });
    cleanupFns.push(() => m.close());

    await m.remember({ content: "Het likes coffee" });
    await m.deleteAgent();
    api.recorded.length = 0;

    await m.remember({ content: "Het likes tea" });

    expect(api.recorded.map((r) => `${r.method} ${r.url}`)).toEqual([
      "GET /api/v2/agents/test-agent",
      "POST /api/v2/agents",
      "POST /api/v2/agents/test-agent/activate",
      "POST /api/v2/agents/test-agent/remember",
    ]);
  });

  it("reads status without bootstrapping an agent session", async () => {
    const api = await startFakeApi();
    cleanupFns.push(api.close);

    const m = new Memanto({ agentId: "test-agent", baseUrl: api.url });
    cleanupFns.push(() => m.close());

    const res = await m.status();
    expect(res).toMatchObject({
      session_id: "existing-session",
      agent_id: "existing-agent",
    });
    expect(api.recorded.map((r) => `${r.method} ${r.url}`)).toEqual([
      "GET /api/v2/status",
    ]);
    expect(api.recorded[0]?.headers["x-session-token"]).toBeUndefined();
  });

  it("streams file uploads with session authentication", async () => {
    const api = await startFakeApi();
    cleanupFns.push(api.close);

    const dir = await mkdtemp(join(tmpdir(), "memanto-sdk-"));
    cleanupFns.push(() => rm(dir, { recursive: true, force: true }));
    const path = join(dir, "notes.txt");
    await writeFile(path, "hello upload");

    const m = new Memanto({ agentId: "test-agent", baseUrl: api.url });
    cleanupFns.push(() => m.close());

    const res = await m.uploadFile({ path });
    expect(res).toMatchObject({ status: "queued", file_name: "notes.txt" });

    const upload = api.recorded.find((r) => r.url.endsWith("/upload-file"));
    expect(upload?.headers["x-session-token"]).toBe("fake-token");
    expect(upload?.headers["content-type"]).toContain(
      "multipart/form-data; boundary=",
    );
    expect(upload?.headers["content-length"]).toBe(
      String(Buffer.byteLength(upload?.body ?? "")),
    );
    expect(upload?.body).toContain('name="file"; filename="notes.txt"');
    expect(upload?.body).toContain("hello upload");
  });

  it("rebuilds a streamed upload after session reactivation", async () => {
    const api = await startFakeApi("test-agent", { expireFirstUpload: true });
    cleanupFns.push(api.close);

    const dir = await mkdtemp(join(tmpdir(), "memanto-sdk-"));
    cleanupFns.push(() => rm(dir, { recursive: true, force: true }));
    const path = join(dir, "notes.txt");
    await writeFile(path, "hello retried upload");

    const m = new Memanto({ agentId: "test-agent", baseUrl: api.url });
    cleanupFns.push(() => m.close());

    const res = await m.uploadFile({ path });

    expect(res).toMatchObject({ status: "queued", file_name: "notes.txt" });
    const activations = api.recorded.filter((r) => r.url.endsWith("/activate"));
    const uploads = api.recorded.filter((r) => r.url.endsWith("/upload-file"));
    expect(activations).toHaveLength(2);
    expect(uploads).toHaveLength(2);
    expect(uploads.map((r) => r.headers["x-session-token"])).toEqual([
      "fake-token",
      "refreshed-token",
    ]);
    expect(uploads.every((r) => r.body.includes("hello retried upload"))).toBe(
      true,
    );
    expect(uploads[0]?.headers["content-type"]).not.toBe(
      uploads[1]?.headers["content-type"],
    );
  });

  it("rejects empty agentId", () => {
    expect(() => new Memanto({ agentId: "" })).toThrow(/agentId is required/);
  });

  it("percent-encodes agentId in URL path segments", async () => {
    const agentId = "team/alpha?mode=prod#frag";
    const api = await startFakeApi(agentId);
    cleanupFns.push(api.close);

    const m = new Memanto({ agentId, baseUrl: api.url });
    cleanupFns.push(() => m.close());

    await m.remember({
      content: "Scoped agent ids must stay in one path segment",
    });

    const encodedAgentId = encodeURIComponent(agentId);
    expect(api.recorded.map((r) => r.url)).toContain(
      `/api/v2/agents/${encodedAgentId}`,
    );
    expect(api.recorded.map((r) => r.url)).toContain(
      `/api/v2/agents/${encodedAgentId}/activate`,
    );
    expect(api.recorded.map((r) => r.url)).toContain(
      `/api/v2/agents/${encodedAgentId}/remember`,
    );

    const create = api.recorded.find(
      (r) => r.method === "POST" && r.url === "/api/v2/agents",
    );
    expect(JSON.parse(create?.body ?? "{}")).toMatchObject({
      agent_id: agentId,
    });
  });
});
