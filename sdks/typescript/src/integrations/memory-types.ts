/**
 * Supported Memanto memory types. Mirrors the server-side
 * `VALID_MEMORY_TYPES` contract so the model can only emit valid values.
 *
 * Shared across framework integrations (Vercel AI SDK, OpenAI, ...).
 */
export const MEMORY_TYPES = [
  "fact",
  "preference",
  "goal",
  "decision",
  "artifact",
  "learning",
  "event",
  "instruction",
  "relationship",
  "context",
  "observation",
  "commitment",
  "error",
] as const;

export type MemoryType = (typeof MEMORY_TYPES)[number];

/** Names of the tools produced by the framework integrations. */
export type MemantoToolName = "recallMemory" | "rememberMemory" | "answerMemory";
