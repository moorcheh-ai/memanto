import { createTool } from "@voltagent/core";
import { z } from "zod";

import type { Memanto } from "../index.js";
import { MEMORY_TYPES, type MemantoToolName, type MemoryType } from "./memory-types.js";

export { MEMORY_TYPES };
export type { MemantoToolName, MemoryType };

export interface CreateMemantoVoltAgentToolsOptions {
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
 * Build VoltAgent tools backed by a {@link Memanto} client.
 *
 * Pass the result straight into an agent's `tools` array:
 *
 * ```ts
 * import { Agent } from "@voltagent/core";
 * import { openai } from "@ai-sdk/openai";
 * import { Memanto } from "@moorcheh-ai/memanto";
 * import { createMemantoVoltAgentTools } from "@moorcheh-ai/memanto/voltagent";
 *
 * const memanto = new Memanto({ agentId: "my-agent" });
 *
 * const agent = new Agent({
 *   name: "Assistant",
 *   instructions:
 *     "You have long-term memory. Persist durable facts with rememberMemory " +
 *     "and look them up with recallMemory / answerMemory before answering.",
 *   model: openai("gpt-4o"),
 *   tools: createMemantoVoltAgentTools(memanto),
 * });
 * ```
 *
 * `@voltagent/core` and `zod` are optional peer dependencies — install them in
 * the host app.
 */
export function createMemantoVoltAgentTools(
  memanto: Memanto,
  options: CreateMemantoVoltAgentToolsOptions = {},
) {
  const { include, defaultLimit } = options;

  const all = {
    recallMemory: createTool({
      name: "recallMemory",
      description:
        "Search the user's long-term memory for relevant facts, preferences, " +
        "decisions, or past context. Call this before answering whenever the " +
        "user refers to information from earlier or from a previous session.",
      parameters: z.object({
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
      name: "rememberMemory",
      description:
        "Persist a durable fact, preference, decision, or instruction that " +
        "will be useful in future sessions. Do not store secrets, credentials, " +
        "or transient chatter.",
      parameters: z.object({
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
      name: "answerMemory",
      description:
        "Answer a question using retrieval-augmented generation over the " +
        "user's stored memories. Prefer this over recallMemory when a direct, " +
        "synthesized answer from memory is more useful than raw results.",
      parameters: z.object({
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

  const names = include ?? (Object.keys(all) as MemantoToolName[]);
  return names.map((name) => all[name]);
}
