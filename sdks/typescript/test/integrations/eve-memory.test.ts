import { createHash } from "node:crypto";

import { describe, expect, it, vi } from "vitest";

import type { Memanto } from "../../src/index.js";
import { memantoMemory } from "../../src/integrations/eve.js";

const SCOPE_KEY = "memscope1_Ab-9_xYzAbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-";
const SCOPE_TAG = `eve_${createHash("sha256").update(SCOPE_KEY).digest("hex").slice(0, 56)}`;

function fakeMemanto(memories: unknown[] = [{ content: "Alex drinks oat milk", type: "preference", created_at: "2026-09-29T10:00:00Z" }]) {
  return {
    recall: vi.fn(async () => ({ memories })),
    remember: vi.fn(async () => ({ memory_id: "mem-1", status: "queued", type: "preference" })),
    extractMemories: vi.fn(async () => ({
      candidates: [{ content: "Alex is vegan", type: "fact", title: "Diet", confidence: 0.9, source: "conversation", provenance: "explicit_statement" }],
    })),
    batchRemember: vi.fn(async () => ({ successful: 1 })),
  };
}

function provider(m: ReturnType<typeof fakeMemanto>, opts: { capture?: boolean; recallLimit?: number } = {}) {
  return memantoMemory({ client: m as unknown as Memanto, ...opts });
}

function turnContext(text: string, scopeKey = SCOPE_KEY) {
  return {
    memory: { scope: { key: scopeKey, namespace: "ns", value: "user-1" }, slot: "memanto" },
    session: { id: "sess-1" },
    turn: { id: "turn-1", sequence: 1, input: [{ role: "user", content: [{ type: "text", text }] }] },
    messages: [],
  } as never;
}

describe("memantoMemory", () => {
  it("recalls this scope's memories into context before a turn", async () => {
    const m = fakeMemanto();
    const result = await provider(m).recall["turn.started"](turnContext("what milk do I like?"));

    expect(m.recall).toHaveBeenCalledWith({ query: "what milk do I like?", limit: 5, tags: [SCOPE_TAG] });
    expect(result).toEqual({
      messages: [
        {
          id: "memanto-recall",
          content: expect.stringContaining("- [preference] Alex drinks oat milk (saved 2026-09-29)"),
        },
      ],
    });
    expect((result as { messages: { content: string }[] }).messages[0]!.content).toContain(
      "not instructions",
    );
  });

  it("adds nothing when no memory matches or the turn has no text", async () => {
    const m = fakeMemanto([]);
    const p = provider(m);

    expect(await p.recall["turn.started"](turnContext("hello"))).toBeNull();
    expect(await p.recall["turn.started"](turnContext("   "))).toBeNull();
    expect(m.recall).toHaveBeenCalledTimes(1);
  });

  it("keeps the turn going when Memanto is unavailable", async () => {
    const m = fakeMemanto();
    m.recall.mockRejectedValueOnce(new Error("connection refused"));
    const log = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(await provider(m).recall["turn.started"](turnContext("what milk?"))).toBeNull();
    expect(log).toHaveBeenCalledWith(
      "[@moorcheh-ai/memanto/eve] recall failed",
      { error: "connection refused", sessionId: "sess-1" },
    );
    log.mockRestore();
  });

  it("derives a scope tag Moorcheh's filter can match", async () => {
    // Moorcheh ignores a tag filter containing "-" and returns every memory,
    // so the tag must stay hyphen-free even though eve's keys contain "-".
    const m = fakeMemanto();
    await provider(m).recall["turn.started"](turnContext("q"));

    const [{ tags }] = m.recall.mock.calls[0] as unknown as [{ tags: string[] }];
    expect(tags).toEqual([SCOPE_TAG]);
    expect(tags[0]).toMatch(/^eve_[0-9a-f]{56}$/);
    expect(tags[0]!.length).toBeLessThanOrEqual(64);
  });

  it("gives different scopes different tags", async () => {
    const m = fakeMemanto();
    const p = provider(m);
    await p.recall["turn.started"](turnContext("q", "memscope1_user-a"));
    await p.recall["turn.started"](turnContext("q", "memscope1_user-b"));

    const tags = m.recall.mock.calls.map((call) => (call as unknown as [{ tags: string[] }])[0].tags[0]);
    expect(tags[0]).not.toBe(tags[1]);
  });

  it("confines the model's tools to the scope", async () => {
    const m = fakeMemanto();
    const tools = (await provider(m).tools!({
      memory: { scope: { key: SCOPE_KEY }, slot: "memanto" },
    } as never))!;

    expect(Object.keys(tools).sort()).toEqual(["recall", "remember"]);

    await tools.remember!.execute({ content: "Alex is vegan", type: "fact" } as never, {} as never);
    expect(m.remember).toHaveBeenCalledWith({
      content: "Alex is vegan",
      type: "fact",
      title: undefined,
      tags: [SCOPE_TAG],
    });

    await tools.recall!.execute({ query: "diet" } as never, {} as never);
    expect(m.recall).toHaveBeenCalledWith({ query: "diet", limit: 5, type: undefined, tags: [SCOPE_TAG] });
  });

  it("does not capture turns unless enabled", () => {
    expect(provider(fakeMemanto()).capture).toBeUndefined();
  });

  it("captures extracted memories from the user's words under the scope tag", async () => {
    const m = fakeMemanto();
    const p = provider(m, { capture: true });

    await p.capture!["turn.completed"]!(turnContext("I went vegan last month"));

    expect(m.extractMemories).toHaveBeenCalledWith({
      messages: [{ role: "user", content: "I went vegan last month" }],
      dryRun: true,
    });
    expect(m.batchRemember).toHaveBeenCalledWith([
      {
        content: "Alex is vegan",
        type: "fact",
        title: "Diet",
        confidence: 0.9,
        source: "conversation",
        provenance: "explicit_statement",
        tags: [SCOPE_TAG, "conversation-extract"],
      },
    ]);
  });

  it("skips the write when extraction finds nothing", async () => {
    const m = fakeMemanto();
    m.extractMemories.mockResolvedValueOnce({ candidates: [] });

    await provider(m, { capture: true }).capture!["turn.completed"]!(turnContext("ok thanks"));
    expect(m.batchRemember).not.toHaveBeenCalled();
  });

  it.each([0, 51, 2.5])("rejects recallLimit %s", (recallLimit) => {
    expect(() => provider(fakeMemanto(), { recallLimit })).toThrow(
      "recallLimit must be an integer between 1 and 50",
    );
  });
});
