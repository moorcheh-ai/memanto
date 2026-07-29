import { describe, expect, it, vi } from "vitest";

import type { Memanto } from "../../src/index.js";
import {
  createMemantoOpenAITools,
  MEMORY_TYPES,
} from "../../src/integrations/openai.js";
import type { MemantoToolName } from "../../src/integrations/openai.js";

/** Minimal stub matching the Memanto surface the tools rely on. */
function fakeMemanto() {
  return {
    recall: vi.fn(async () => ({ memories: [{ content: "Alex drinks oat milk" }] })),
    remember: vi.fn(async () => ({ memory_id: "mem-1", status: "queued" })),
    answer: vi.fn(async () => ({ answer: "Oat milk.", sources: [] })),
  };
}

type OpenAITool = ReturnType<typeof createMemantoOpenAITools>[number];

function byName(tools: OpenAITool[], name: MemantoToolName): OpenAITool {
  const found = tools.find((t) => t.function.name === name);
  if (!found) throw new Error(`tool ${name} not found`);
  return found;
}

/** Invoke the runTools callback the OpenAI SDK would call after parsing args. */
async function invoke(tool: OpenAITool, args: unknown): Promise<unknown> {
  return tool.$callback!(args as never);
}

describe("createMemantoOpenAITools", () => {
  it("creates all three tools by default", () => {
    const tools = createMemantoOpenAITools(fakeMemanto() as unknown as Memanto);
    expect(tools.map((t) => t.function.name).sort()).toEqual([
      "answerMemory",
      "recallMemory",
      "rememberMemory",
    ]);
  });

  it("produces auto-parseable function tools", () => {
    const tools = createMemantoOpenAITools(fakeMemanto() as unknown as Memanto);
    for (const t of tools) {
      expect(t.type).toBe("function");
      expect(typeof t.function.description).toBe("string");
      expect(t.$brand).toBe("auto-parseable-tool");
    }
  });

  it("respects the include filter and preserves order", () => {
    const tools = createMemantoOpenAITools(fakeMemanto() as unknown as Memanto, {
      include: ["answerMemory", "recallMemory"],
    });
    expect(tools.map((t) => t.function.name)).toEqual([
      "answerMemory",
      "recallMemory",
    ]);
  });

  it("recallMemory returns the memories array and forwards limit/type", async () => {
    const m = fakeMemanto();
    const tools = createMemantoOpenAITools(m as unknown as Memanto, {
      defaultLimit: 8,
    });

    const result = await invoke(byName(tools, "recallMemory"), {
      query: "what milk?",
      type: ["preference"],
    });

    expect(result).toEqual([{ content: "Alex drinks oat milk" }]);
    expect(m.recall).toHaveBeenCalledWith({
      query: "what milk?",
      limit: 8,
      type: ["preference"],
    });
  });

  it("rememberMemory forwards content and type", async () => {
    const m = fakeMemanto();
    const tools = createMemantoOpenAITools(m as unknown as Memanto);

    const result = await invoke(byName(tools, "rememberMemory"), {
      content: "Alex switched to soy",
      type: "preference",
    });

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
    const tools = createMemantoOpenAITools(m as unknown as Memanto, {
      defaultLimit: 12,
    });

    await invoke(byName(tools, "answerMemory"), {
      question: "Does Alex drink dairy?",
    });

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
