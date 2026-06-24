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

function startFakeApi(): Promise<{
  url: string;
  recorded: Recorded[];
  close: () => void;
}> {
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
        if (url.startsWith("/api/v2/agents/test-agent/activate"))
          return reply(200, {
            session_token: "fake-token",
            agent_id: "test-agent",
            session_id: "sess-1",
            namespace: "memanto_agent_test_agent",
            started_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 3600_000).toISOString(),
            status: "active",
            pattern: "default",
          });
        if (url === "/api/v2/agents/test-agent" && req.method === "GET")
          return reply(404, { detail: "not found" });
        if (url === "/api/v2/agents" && req.method === "POST")
          return reply(201, { agent_id: "test-agent" });
        if (url === "/api/v2/agents/test-agent/remember")
          return reply(200, {
            memory_id: "mem-1",
            agent_id: "test-agent",
            session_id: "sess-1",
            namespace: "memanto_agent_test_agent",
            status: "queued",
            provenance: "explicit_statement",
            confidence: 0.9,
            type: "fact",
          });
        if (url === "/api/v2/agents/test-agent/recall")
          return reply(200, {
            agent_id: "test-agent",
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

  it("rejects empty agentId", () => {
    expect(() => new Memanto({ agentId: "" })).toThrow(/agentId is required/);
  });
});
