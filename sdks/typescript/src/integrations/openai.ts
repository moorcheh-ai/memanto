import { zodFunction } from "openai/helpers/zod";
import { z } from "zod";

import type { Memanto } from "../index.js";
import { MEMORY_TYPES, type MemantoToolName, type MemoryType } from "./memory-types.js";

export { MEMORY_TYPES };
export type { MemantoToolName, MemoryType };

export interface CreateMemantoOpenAIToolsOptions {
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
 * Build OpenAI tools backed by a {@link Memanto} client, ready to hand to the
 * OpenAI Node SDK's `runTools()` helper. Each tool auto-parses its JSON
 * arguments against a Zod schema before invoking Memanto.
 *
 * ```ts
 * import OpenAI from "openai";
 * import { Memanto } from "@moorcheh-ai/memanto";
 * import { createMemantoOpenAITools } from "@moorcheh-ai/memanto/openai";
 *
 * const client = new OpenAI();
 * const memanto = new Memanto({ agentId: "my-agent" });
 *
 * const runner = client.chat.completions.runTools({
 *   model: "gpt-4o",
 *   tools: createMemantoOpenAITools(memanto),
 *   messages: [
 *     { role: "user", content: "What milk does Alex like? Also note he switched to soy today." },
 *   ],
 * });
 *
 * console.log(await runner.finalContent());
 * ```
 *
 * `openai` and `zod` are optional peer dependencies — install them in the host app.
 */
export function createMemantoOpenAITools(
  memanto: Memanto,
  options: CreateMemantoOpenAIToolsOptions = {},
) {
  const { include, defaultLimit } = options;

  const all = {
    recallMemory: zodFunction({
      name: "recallMemory",
      description:
        "Search the user's long-term memory for relevant facts, preferences, " +
        "decisions, or past context. Call this before answering whenever the " +
        "user refers to information from earlier or from a previous session.",
      parameters: z.object({
        query: z
          .string()
          .describe("Natural-language description of what to recall"),
        limit: z
          .number()
          .int()
          .nullable()
          .describe("Maximum number of memories to return, or null for the default"),
        type: z
          .array(z.enum(MEMORY_TYPES))
          .nullable()
          .describe("Filter restricting results to these memory types, or null for no filter"),
      }),
      function: async ({ query, limit, type }) => {
        const res = (await memanto.recall({
          query,
          limit: limit ?? defaultLimit,
          type: type ?? undefined,
        })) as { memories?: unknown };
        return res.memories ?? res;
      },
    }),

    rememberMemory: zodFunction({
      name: "rememberMemory",
      description:
        "Persist a durable fact, preference, decision, or instruction that " +
        "will be useful in future sessions. Do not store secrets, credentials, " +
        "or transient chatter.",
      parameters: z.object({
        content: z.string().describe("The information to remember"),
        type: z
          .enum(MEMORY_TYPES)
          .nullable()
          .describe("Memory type, or null to let the server auto-classify."),
        title: z.string().nullable().describe("Short title, or null"),
        tags: z
          .array(z.string())
          .nullable()
          .describe("Tags for later filtering, or null"),
      }),
      function: async ({ content, type, title, tags }) =>
        memanto.remember({
          content,
          type: type ?? undefined,
          title: title ?? undefined,
          tags: tags ?? undefined,
        }),
    }),

    answerMemory: zodFunction({
      name: "answerMemory",
      description:
        "Answer a question using retrieval-augmented generation over the " +
        "user's stored memories. Prefer this over recallMemory when a direct, " +
        "synthesized answer from memory is more useful than raw results.",
      parameters: z.object({
        question: z.string().describe("The question to answer from memory"),
        limit: z
          .number()
          .int()
          .nullable()
          .describe("Number of context memories to use, or null for the default"),
      }),
      function: async ({ question, limit }) =>
        memanto.answer({ question, limit: limit ?? defaultLimit }),
    }),
  };

  const names = include ?? (Object.keys(all) as MemantoToolName[]);
  return names.map((name) => all[name]);
}
