import { describe, expect, it, vi } from "vitest";

import type { Memanto } from "../../src/index.js";
import { createMemantoTools, MEMORY_TYPES } from "../../src/integrations/ai-sdk.js";

/** Minimal stub matching the Memanto surface the tools rely on. */
function fakeMemanto() {
  return {
    recall: vi.fn(async () => ({ memories: [{ content: "Alex drinks oat milk" }] })),
    remember: vi.fn(async () => ({ memory_id: "mem-1", status: "queued" })),
    answer: vi.fn(async () => ({ answer: "Oat milk.", sources: [] })),
  };
}

/** AI SDK passes a second options arg to execute; tests don't need it. */
const execOpts = {} as never;

describe("createMemantoTools", () => {
  it("creates all three tools by default", () => {
    const tools = createMemantoTools(fakeMemanto() as unknown as Memanto);
    expect(Object.keys(tools).sort()).toEqual([
      "answerMemory",
      "recallMemory",
      "rememberMemory",
    ]);
  });

  it("respects the include filter", () => {
    const tools = createMemantoTools(fakeMemanto() as unknown as Memanto, {
      include: ["recallMemory"],
    });
    expect(Object.keys(tools)).toEqual(["recallMemory"]);
  });

  it("recallMemory returns the memories array and forwards limit/type", async () => {
    const m = fakeMemanto();
    const tools = createMemantoTools(m as unknown as Memanto, { defaultLimit: 8 });

    const result = await tools.recallMemory!.execute!(
      { query: "what milk?", type: ["preference"] },
      execOpts,
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
    const tools = createMemantoTools(m as unknown as Memanto);

    const result = await tools.rememberMemory!.execute!(
      { content: "Alex switched to soy", type: "preference" },
      execOpts,
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
    const tools = createMemantoTools(m as unknown as Memanto, { defaultLimit: 12 });

    await tools.answerMemory!.execute!({ question: "Does Alex drink dairy?" }, execOpts);

    expect(m.answer).toHaveBeenCalledWith({
      question: "Does Alex drink dairy?",
      limit: 12,
    });
  });

  it("exposes the server memory-type contract", () => {
    expect(MEMORY_TYPES).toContain("fact");
    expect(MEMORY_TYPES).toContain("preference");
  });
});
