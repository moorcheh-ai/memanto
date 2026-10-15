import { describe, expect, it, vi } from "vitest";

import type { Memanto } from "../../src/index.js";
import { createMemantoEveTools, MEMORY_TYPES } from "../../src/integrations/eve.js";

/** Minimal stub matching the Memanto surface the tools rely on. */
function fakeMemanto() {
  return {
    recall: vi.fn(async () => ({ memories: [{ content: "Alex drinks oat milk" }] })),
    remember: vi.fn(async () => ({ memory_id: "mem-1", status: "queued" })),
    answer: vi.fn(async () => ({ answer: "Oat milk.", sources: [] })),
  };
}

describe("createMemantoEveTools", () => {
  it("creates all three tools by default", () => {
    const tools = createMemantoEveTools(fakeMemanto() as unknown as Memanto);
    expect(Object.keys(tools).sort()).toEqual([
      "answerMemory",
      "recallMemory",
      "rememberMemory",
    ]);
  });

  it("respects the include filter", () => {
    const tools = createMemantoEveTools(fakeMemanto() as unknown as Memanto, {
      include: ["recallMemory"],
    });
    expect(Object.keys(tools)).toEqual(["recallMemory"]);
  });

  it("recallMemory returns the memories array and forwards limit/type", async () => {
    const m = fakeMemanto();
    const tools = createMemantoEveTools(m as unknown as Memanto, {
      defaultLimit: 8,
    });

    const result = await tools.recallMemory!.execute!(
      { query: "what milk?", type: ["preference"] },
      {} as never,
    );

    expect(result).toEqual([{ content: "Alex drinks oat milk" }]);
    expect(m.recall).toHaveBeenCalledWith({
      query: "what milk?",
      limit: 8,
      type: ["preference"],
    });
  });

  it("rememberMemory forwards content and type", async () => {
    const m = fakeMemanto();
    const tools = createMemantoEveTools(m as unknown as Memanto);

    const result = await tools.rememberMemory!.execute!(
      { content: "Alex switched to soy", type: "preference" },
      {} as never,
    );

    expect(result).toMatchObject({ memory_id: "mem-1" });
    expect(m.remember).toHaveBeenCalledWith({
      content: "Alex switched to soy",
      type: "preference",
      title: undefined,
      tags: undefined,
    });
  });

  it("answerMemory falls back to defaultLimit", async () => {
    const m = fakeMemanto();
    const tools = createMemantoEveTools(m as unknown as Memanto, {
      defaultLimit: 12,
    });

    await tools.answerMemory!.execute!({ question: "Does Alex drink dairy?" }, {} as never);

    expect(m.answer).toHaveBeenCalledWith({
      question: "Does Alex drink dairy?",
      limit: 12,
    });
  });

  it("labels tool activity for channels", () => {
    const tools = createMemantoEveTools(fakeMemanto() as unknown as Memanto);

    expect(tools.recallMemory!.label!.start({ query: "what milk?" })).toBe(
      'Recalling "what milk?"',
    );
    expect(tools.recallMemory!.label!.complete!({ query: "q" }, [])).toBe(
      "No matching memories",
    );
    expect(
      tools.recallMemory!.label!.complete!({ query: "q" }, [{ content: "a" }]),
    ).toBe("Found 1 memory");
    expect(
      tools.rememberMemory!.label!.complete!(
        { content: "x" },
        { memory_id: "m", status: "queued", type: "preference" },
      ),
    ).toBe("Saved to memory as preference");
    expect(
      tools.answerMemory!.label!.complete!(
        { question: "q" },
        { answer: "a", sources: [{}, {}] },
      ),
    ).toBe("Answered from 2 memories");
  });

  it("clips long input in labels to one line", () => {
    const tools = createMemantoEveTools(fakeMemanto() as unknown as Memanto);
    const label = tools.rememberMemory!.label!.start({
      content: `Alex\nprefers ${"oat ".repeat(40)}`,
    });

    expect(label).not.toContain("\n");
    expect(label.length).toBeLessThanOrEqual('Remembering ""'.length + 60);
    expect(label.endsWith('…"')).toBe(true);
  });

  it("gives the model a compact view of recalled memories", async () => {
    const tools = createMemantoEveTools(fakeMemanto() as unknown as Memanto);
    const toModel = tools.recallMemory!.toModelOutput!;

    expect(
      await toModel([
        {
          id: "mem-1",
          content: "Alex drinks oat milk",
          type: "preference",
          confidence: 0.8,
          created_at: "2026-09-29T00:00:00Z",
          text: "[PREFERENCE] Alex drinks oat milk",
          tags: [],
          expired_at: null,
        } as never,
      ]),
    ).toEqual({
      type: "json",
      value: [
        {
          id: "mem-1",
          type: "preference",
          content: "Alex drinks oat milk",
          confidence: 0.8,
          created_at: "2026-09-29T00:00:00Z",
        },
      ],
    });
    expect(await toModel([])).toEqual({
      type: "text",
      value: "No matching memories found.",
    });
  });

  it("gives the model only the answer text and the saved memory id", async () => {
    const tools = createMemantoEveTools(fakeMemanto() as unknown as Memanto);

    expect(
      await tools.answerMemory!.toModelOutput!({ answer: "Oat milk.", sources: [] }),
    ).toEqual({ type: "text", value: "Oat milk." });
    expect(
      await tools.rememberMemory!.toModelOutput!({
        memory_id: "mem-1",
        status: "queued",
        type: "preference",
        agent_id: "a",
        session_id: "s",
      } as never),
    ).toEqual({
      type: "json",
      value: { memory_id: "mem-1", type: "preference", status: "queued" },
    });
  });

  it.each([0, -1, 1.5, 51, Number.NaN])(
    "rejects invalid defaultLimit %s before creating tools",
    (defaultLimit) => {
      expect(() =>
        createMemantoEveTools(fakeMemanto() as unknown as Memanto, {
          defaultLimit,
        }),
      ).toThrow("defaultLimit must be an integer between 1 and 50");
    },
  );

  it("exposes the server memory-type contract", () => {
    expect(MEMORY_TYPES).toContain("fact");
    expect(MEMORY_TYPES).toContain("preference");
  });
});
