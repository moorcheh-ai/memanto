import { afterEach, describe, expect, it } from "vitest";
import { createServer, type Server, type IncomingMessage } from "node:http";
import { AddressInfo } from "node:net";
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

  it("rejects empty agentId", () => {
    expect(() => new Memanto({ agentId: "" })).toThrow(/agentId is required/);
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
