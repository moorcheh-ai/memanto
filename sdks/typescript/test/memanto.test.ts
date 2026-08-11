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

function startFakeApi(agentId = "test-agent"): Promise<{
  url: string;
  recorded: Recorded[];
  close: () => void;
}> {
  return startFakeApiWithAuth(agentId, null);
}

/**
 * Variant of the fake API that enforces `X-Api-Key` on management endpoints.
 * When `requiredKey` is set, agent lookup/creation/activation/deletion/status
 * return 401 unless the request carries the matching key. Memory endpoints
 * stay open to any caller so the session-token path is unaffected.
 */
function startFakeApiWithAuth(
  agentId = "test-agent",
  requiredKey: string | null,
): Promise<{
  url: string;
  recorded: Recorded[];
  close: () => void;
}> {
  const encodedAgentId = encodeURIComponent(agentId);
  return new Promise((resolve) => {
    const recorded: Recorded[] = [];
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

        const isMemoryOp =
          /\/remember(\/|$|\?)/.test(url) ||
          /\/recall(\/|$|\?)/.test(url) ||
          /\/answer(\/|$|\?)/.test(url) ||
          /\/upload-file(\/|$|\?)/.test(url) ||
          /\/daily-summary(\/|$|\?)/.test(url) ||
          /\/conflicts(\/|$|\?)/.test(url) ||
          /\/memories(\/|$|\?)/.test(url) ||
          /\/extract(\/|$|\?)/.test(url);
        const isManagement =
          !isMemoryOp &&
          (url === "/api/v2/status" ||
            url === "/api/v2/agents" ||
            url.startsWith(`/api/v2/agents/${encodedAgentId}`));
        if (isManagement && requiredKey) {
          const supplied = req.headers["x-api-key"];
          if (supplied !== requiredKey) {
            return reply(401, { detail: "missing or invalid api key" });
          }
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
        if (url.startsWith(`/api/v2/agents/${encodedAgentId}/activate`))
          return reply(200, {
            session_token: "fake-token",
            agent_id: agentId,
            session_id: "sess-1",
            namespace: "memanto_agent_test_agent",
            started_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 3600_000).toISOString(),
            status: "active",
            pattern: "default",
          });
        if (url === `/api/v2/agents/${encodedAgentId}` && req.method === "GET")
          return reply(404, { detail: "not found" });
        if (url === "/api/v2/agents" && req.method === "POST")
          return reply(201, { agent_id: agentId });
        if (url === `/api/v2/agents/${encodedAgentId}` && req.method === "DELETE")
          return reply(200, { agent_id: agentId, deleted: true });
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
        )
          return reply(200, {
            agent_id: agentId,
            session_id: "sess-1",
            status: "queued",
            file_name: "notes.txt",
          });
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

    const remember = api.recorded.find((r) =>
      r.url.endsWith("/remember"),
    );
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

    const upload = api.recorded.find((r) =>
      r.url.endsWith("/upload-file"),
    );
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

  it("rejects empty agentId", () => {
    expect(() => new Memanto({ agentId: "" })).toThrow(/agentId is required/);
  });

  it("attaches X-Api-Key to management requests but not memory ops", async () => {
    const api = await startFakeApi();
    cleanupFns.push(api.close);

    const m = new Memanto({
      agentId: "test-agent",
      baseUrl: api.url,
      apiKey: "secret-mgmt-key",
    });
    cleanupFns.push(() => m.close());

    await m.remember({ content: "Het likes coffee" });

    // Management calls: agent lookup, creation, activation.
    const mgmt = api.recorded.filter((r) => !r.url.endsWith("/remember"));
    expect(mgmt.length).toBeGreaterThanOrEqual(3);
    for (const r of mgmt) {
      expect(r.headers["x-api-key"]).toBe("secret-mgmt-key");
      expect(r.headers["x-session-token"]).toBeUndefined();
    }

    // Session-scoped memory call: X-Session-Token only, never the API key.
    const memory = api.recorded.find((r) => r.url.endsWith("/remember"));
    expect(memory?.headers["x-session-token"]).toBe("fake-token");
    expect(memory?.headers["x-api-key"]).toBeUndefined();
  });

  it("authenticates management requests against a protected server", async () => {
    const api = await startFakeApiWithAuth("test-agent", "secret-mgmt-key");
    cleanupFns.push(api.close);

    // First, a client WITHOUT the API key fails bootstrap with 401.
    const anonymous = new Memanto({ agentId: "test-agent", baseUrl: api.url });
    cleanupFns.push(() => anonymous.close());
    await expect(anonymous.remember({ content: "no key" })).rejects.toThrow(
      /401/,
    );

    // Then the same bootstrap succeeds when the key is provided.
    api.recorded.length = 0;
    const authed = new Memanto({
      agentId: "test-agent",
      baseUrl: api.url,
      apiKey: "secret-mgmt-key",
    });
    cleanupFns.push(() => authed.close());
    await expect(
      authed.remember({ content: "with key" }),
    ).resolves.toMatchObject({ memory_id: "mem-1" });
  });

  it("does not send X-Api-Key when none is configured", async () => {
    const api = await startFakeApi();
    cleanupFns.push(api.close);

    const m = new Memanto({ agentId: "test-agent", baseUrl: api.url });
    cleanupFns.push(() => m.close());

    await m.status();
    expect(api.recorded[0]?.headers["x-api-key"]).toBeUndefined();
  });

  it("percent-encodes agentId in URL path segments", async () => {
    const agentId = "team/alpha?mode=prod#frag";
    const api = await startFakeApi(agentId);
    cleanupFns.push(api.close);

    const m = new Memanto({ agentId, baseUrl: api.url });
    cleanupFns.push(() => m.close());

    await m.remember({ content: "Scoped agent ids must stay in one path segment" });

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
    expect(JSON.parse(create?.body ?? "{}")).toMatchObject({ agent_id: agentId });
  });
});
