import { createTool } from "@mastra/core/tools";
import { z } from "zod";

import type { Memanto } from "../index.js";
import { MEMORY_TYPES, type MemantoToolName, type MemoryType } from "./memory-types.js";

export { MEMORY_TYPES };
export type { MemantoToolName, MemoryType };

export interface CreateMemantoMastraToolsOptions {
  /**
   * Which tools to create. Defaults to all of them. Pass a subset to expose
   * only, say, read access: `{ include: ["recallMemory"] }`.
   */
  include?: MemantoToolName[];
  /**
   * Default result limit applied to `recallMemory` / `answerMemory` when the
   * model does not specify one. Falls back to the server default when omitted.
   */
  defaultLimit?: number;
}

/**
 * Build Mastra tools backed by a {@link Memanto} client.
 *
 * Pass the result straight into an agent's `tools` map:
 *
 * ```ts
 * import { Agent } from "@mastra/core/agent";
 * import { Memanto } from "@moorcheh-ai/memanto";
 * import { createMemantoMastraTools } from "@moorcheh-ai/memanto/mastra";
 *
 * const memanto = new Memanto({ agentId: "my-agent" });
 *
 * const agent = new Agent({
 *   id: "assistant",
 *   name: "Assistant",
 *   instructions:
 *     "You have long-term memory. Persist durable facts with rememberMemory " +
 *     "and look them up with recallMemory / answerMemory before answering.",
 *   model: "openai/gpt-4o",
 *   tools: createMemantoMastraTools(memanto),
 * });
 * ```
 *
 * `@mastra/core` and `zod` are optional peer dependencies — install them in
 * the host app.
 */
export function createMemantoMastraTools(
  memanto: Memanto,
  options: CreateMemantoMastraToolsOptions = {},
) {
  const { include, defaultLimit } = options;

  const all = {
    recallMemory: createTool({
      id: "recallMemory",
      description:
        "Search the user's long-term memory for relevant facts, preferences, " +
        "decisions, or past context. Call this before answering whenever the " +
        "user refers to information from earlier or from a previous session.",
      inputSchema: z.object({
        query: z
          .string()
          .min(1)
          .describe("Natural-language description of what to recall"),
        limit: z
          .number()
          .int()
          .min(1)
          .max(50)
          .optional()
          .describe("Maximum number of memories to return"),
        type: z
          .array(z.enum(MEMORY_TYPES))
          .optional()
          .describe("Optional filter restricting results to these memory types"),
      }),
      execute: async ({ query, limit, type }) => {
        const res = (await memanto.recall({
          query,
          limit: limit ?? defaultLimit,
          type,
        })) as { memories?: unknown };
        return res.memories ?? res;
      },
    }),

    rememberMemory: createTool({
      id: "rememberMemory",
      description:
        "Persist a durable fact, preference, decision, or instruction that " +
        "will be useful in future sessions. Do not store secrets, credentials, " +
        "or transient chatter.",
      inputSchema: z.object({
        content: z.string().min(1).describe("The information to remember"),
        type: z
          .enum(MEMORY_TYPES)
          .optional()
          .describe("Memory type. Omit to let the server auto-classify."),
        title: z.string().optional().describe("Optional short title"),
        tags: z
          .array(z.string())
          .optional()
          .describe("Optional tags for later filtering"),
      }),
      execute: async ({ content, type, title, tags }) =>
        memanto.remember({ content, type, title, tags }),
    }),

    answerMemory: createTool({
      id: "answerMemory",
      description:
        "Answer a question using retrieval-augmented generation over the " +
        "user's stored memories. Prefer this over recallMemory when a direct, " +
        "synthesized answer from memory is more useful than raw results.",
      inputSchema: z.object({
        question: z
          .string()
          .min(1)
          .describe("The question to answer from memory"),
        limit: z
          .number()
          .int()
          .min(1)
          .max(100)
          .optional()
          .describe("Number of context memories to use"),
      }),
      execute: async ({ question, limit }) =>
        memanto.answer({ question, limit: limit ?? defaultLimit }),
    }),
  };

  if (!include) return all;

  const selected = {} as Partial<typeof all>;
  for (const name of Object.keys(all) as MemantoToolName[]) {
    if (include.includes(name)) {
      (selected as Record<MemantoToolName, (typeof all)[MemantoToolName]>)[name] =
        all[name];
    }
  }
  return selected;
}
