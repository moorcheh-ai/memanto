import { describe, expect, it, vi } from "vitest";

import type { Memanto } from "../../src/index.js";
import {
  createMemantoComposioTools,
  MEMORY_TYPES,
} from "../../src/integrations/composio.js";

/** Minimal stub matching the Memanto surface the tools rely on. */
function fakeMemanto() {
  return {
    recall: vi.fn(async () => ({ memories: [{ content: "Alex drinks oat milk" }] })),
    remember: vi.fn(async () => ({ memory_id: "mem-1", status: "queued" })),
    answer: vi.fn(async () => ({ answer: "Oat milk.", sources: [] })),
  };
}

/**
 * Minimal stub matching the `composio.tools.createCustomTool` surface. It
 * just echoes back the registration options so tests can grab `execute`
 * straight off the returned "tool".
 */
function fakeComposio() {
  return {
    tools: {
      createCustomTool: vi.fn(async (body: Record<string, unknown>) => body),
    },
  };
}

describe("createMemantoComposioTools", () => {
  it("creates all three tools by default", async () => {
    const tools = await createMemantoComposioTools(
      fakeMemanto() as unknown as Memanto,
      fakeComposio() as never,
    );
    expect(Object.keys(tools).sort()).toEqual([
      "answerMemory",
      "recallMemory",
      "rememberMemory",
    ]);
  });

  it("respects the include filter", async () => {
    const composio = fakeComposio();
    const tools = await createMemantoComposioTools(
      fakeMemanto() as unknown as Memanto,
      composio as never,
      { include: ["recallMemory"] },
    );
    expect(Object.keys(tools)).toEqual(["recallMemory"]);
    expect(composio.tools.createCustomTool).toHaveBeenCalledTimes(1);
  });

  it("recallMemory returns the memories array wrapped in a successful result and forwards limit/type", async () => {
    const m = fakeMemanto();
    const tools = await createMemantoComposioTools(m as unknown as Memanto, fakeComposio() as never, {
      defaultLimit: 8,
    });

    const result = await (tools.recallMemory as unknown as { execute: (input: unknown) => Promise<unknown> }).execute({
      query: "what milk?",
      type: ["preference"],
    });

    expect(result).toEqual({
      data: { result: [{ content: "Alex drinks oat milk" }] },
      error: null,
      successful: true,
    });
    expect(m.recall).toHaveBeenCalledWith({
      query: "what milk?",
      limit: 8,
      type: ["preference"],
    });
  });

  it("rememberMemory forwards content and type", async () => {
    const m = fakeMemanto();
    const tools = await createMemantoComposioTools(m as unknown as Memanto, fakeComposio() as never);

    const result = await (tools.rememberMemory as unknown as { execute: (input: unknown) => Promise<unknown> }).execute({
      content: "Alex switched to soy",
      type: "preference",
    });

    expect(result).toMatchObject({
      data: { result: { memory_id: "mem-1" } },
      successful: true,
    });
    expect(m.remember).toHaveBeenCalledWith({
      content: "Alex switched to soy",
      type: "preference",
      title: undefined,
      tags: undefined,
    });
  });

  it("answerMemory falls back to defaultLimit", async () => {
    const m = fakeMemanto();
    const tools = await createMemantoComposioTools(m as unknown as Memanto, fakeComposio() as never, {
      defaultLimit: 12,
    });

    await (tools.answerMemory as unknown as { execute: (input: unknown) => Promise<unknown> }).execute({
      question: "Does Alex drink dairy?",
    });

    expect(m.answer).toHaveBeenCalledWith({
      question: "Does Alex drink dairy?",
      limit: 12,
    });
  });

  it("wraps a failed memanto call into an unsuccessful tool result", async () => {
    const m = fakeMemanto();
    m.recall.mockRejectedValueOnce(new Error("server unreachable"));
    const tools = await createMemantoComposioTools(m as unknown as Memanto, fakeComposio() as never);

    const result = await (tools.recallMemory as unknown as { execute: (input: unknown) => Promise<unknown> }).execute({
      query: "what milk?",
    });

    expect(result).toEqual({ data: {}, error: "server unreachable", successful: false });
  });

  it("exposes the server memory-type contract", () => {
    expect(MEMORY_TYPES).toContain("fact");
    expect(MEMORY_TYPES).toContain("preference");
  });
});
