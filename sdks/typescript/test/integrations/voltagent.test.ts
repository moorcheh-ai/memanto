import { describe, expect, it, vi } from "vitest";

import type { Memanto } from "../../src/index.js";
import {
  createMemantoVoltAgentTools,
  MEMORY_TYPES,
} from "../../src/integrations/voltagent.js";
import type { MemantoToolName } from "../../src/integrations/voltagent.js";

/** Minimal stub matching the Memanto surface the tools rely on. */
function fakeMemanto() {
  return {
    recall: vi.fn(async () => ({ memories: [{ content: "Alex drinks oat milk" }] })),
    remember: vi.fn(async () => ({ memory_id: "mem-1", status: "queued" })),
    answer: vi.fn(async () => ({ answer: "Oat milk.", sources: [] })),
  };
}

type VoltAgentTool = ReturnType<typeof createMemantoVoltAgentTools>[number];

function byName(tools: VoltAgentTool[], name: MemantoToolName): VoltAgentTool {
  const found = tools.find((t) => t.name === name);
  if (!found) throw new Error(`tool ${name} not found`);
  return found;
}

/** VoltAgent passes a second options arg to execute; tests don't need it. */
const execOpts = {} as never;

describe("createMemantoVoltAgentTools", () => {
  it("creates all three tools by default", () => {
    const tools = createMemantoVoltAgentTools(fakeMemanto() as unknown as Memanto);
    expect(tools.map((t) => t.name).sort()).toEqual([
      "answerMemory",
      "recallMemory",
      "rememberMemory",
    ]);
  });

  it("respects the include filter and preserves order", () => {
    const tools = createMemantoVoltAgentTools(fakeMemanto() as unknown as Memanto, {
      include: ["answerMemory", "recallMemory"],
    });
    expect(tools.map((t) => t.name)).toEqual(["answerMemory", "recallMemory"]);
  });

  it("recallMemory returns the memories array and forwards limit/type", async () => {
    const m = fakeMemanto();
    const tools = createMemantoVoltAgentTools(m as unknown as Memanto, {
      defaultLimit: 8,
    });

    const result = await byName(tools, "recallMemory").execute!(
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
    const tools = createMemantoVoltAgentTools(m as unknown as Memanto);

    const result = await byName(tools, "rememberMemory").execute!(
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
    const tools = createMemantoVoltAgentTools(m as unknown as Memanto, {
      defaultLimit: 12,
    });

    await byName(tools, "answerMemory").execute!(
      { question: "Does Alex drink dairy?" },
      execOpts,
    );

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
