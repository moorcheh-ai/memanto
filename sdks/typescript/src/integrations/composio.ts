import type { Composio, Tool } from "@composio/core";
// `@composio/core`'s custom-tool types are built on zod's v3-compat subpath,
// so schemas here must use the same `z` or TypeScript sees two unrelated
// `ZodType`s.
import { z } from "zod/v3";

import type { Memanto } from "../index.js";
import { MEMORY_TYPES, type MemantoToolName, type MemoryType } from "./memory-types.js";

export { MEMORY_TYPES };
export type { MemantoToolName, MemoryType };

export interface CreateMemantoComposioToolsOptions {
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

function ok(result: unknown) {
  return { data: { result }, error: null, successful: true } as const;
}

function fail(err: unknown) {
  return {
    data: {},
    error: err instanceof Error ? err.message : String(err),
    successful: false,
  } as const;
}

/**
 * Register Composio custom tools backed by a {@link Memanto} client.
 *
 * Composio custom tools are registered against a live `Composio` client
 * instance (`composio.tools.createCustomTool`), so this registers them for
 * you and hands back the created {@link Tool} objects:
 *
 * ```ts
 * import { Composio } from "@composio/core";
 * import { Memanto } from "@moorcheh-ai/memanto";
 * import { createMemantoComposioTools } from "@moorcheh-ai/memanto/composio";
 *
 * const memanto = new Memanto({ agentId: "my-agent" });
 * const composio = new Composio();
 *
 * const tools = await createMemantoComposioTools(memanto, composio);
 * // tools.recallMemory / tools.rememberMemory / tools.answerMemory
 * ```
 *
 * `@composio/core` and `zod` are optional peer dependencies — install them in
 * the host app.
 */
export async function createMemantoComposioTools(
  memanto: Memanto,
  composio: Composio,
  options: CreateMemantoComposioToolsOptions = {},
): Promise<Partial<Record<MemantoToolName, Tool>>> {
  const { include, defaultLimit } = options;
  const wants = (name: MemantoToolName) => !include || include.includes(name);

  const tools: Partial<Record<MemantoToolName, Tool>> = {};

  if (wants("recallMemory")) {
    tools.recallMemory = await composio.tools.createCustomTool({
      slug: "MEMANTO_RECALL_MEMORY",
      name: "Recall memory",
      description:
        "Search the user's long-term memory for relevant facts, preferences, " +
        "decisions, or past context. Call this before answering whenever the " +
        "user refers to information from earlier or from a previous session.",
      inputParams: z.object({
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
      execute: async ({
        query,
        limit,
        type,
      }: {
        query: string;
        limit?: number;
        type?: MemoryType[];
      }) => {
        try {
          const res = (await memanto.recall({
            query,
            limit: limit ?? defaultLimit,
            type,
          })) as { memories?: unknown };
          return ok(res.memories ?? res);
        } catch (err) {
          return fail(err);
        }
      },
    });
  }

  if (wants("rememberMemory")) {
    tools.rememberMemory = await composio.tools.createCustomTool({
      slug: "MEMANTO_REMEMBER_MEMORY",
      name: "Remember memory",
      description:
        "Persist a durable fact, preference, decision, or instruction that " +
        "will be useful in future sessions. Do not store secrets, credentials, " +
        "or transient chatter.",
      inputParams: z.object({
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
      execute: async ({
        content,
        type,
        title,
        tags,
      }: {
        content: string;
        type?: MemoryType;
        title?: string;
        tags?: string[];
      }) => {
        try {
          const res = await memanto.remember({ content, type, title, tags });
          return ok(res);
        } catch (err) {
          return fail(err);
        }
      },
    });
  }

  if (wants("answerMemory")) {
    tools.answerMemory = await composio.tools.createCustomTool({
      slug: "MEMANTO_ANSWER_MEMORY",
      name: "Answer from memory",
      description:
        "Answer a question using retrieval-augmented generation over the " +
        "user's stored memories. Prefer this over recallMemory when a direct, " +
        "synthesized answer from memory is more useful than raw results.",
      inputParams: z.object({
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
      execute: async ({ question, limit }: { question: string; limit?: number }) => {
        try {
          const res = await memanto.answer({ question, limit: limit ?? defaultLimit });
          return ok(res);
        } catch (err) {
          return fail(err);
        }
      },
    });
  }

  return tools;
}
