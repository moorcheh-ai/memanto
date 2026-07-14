import { readFile } from "node:fs/promises";
import { basename } from "node:path";

import { ServerLifecycle, type ServerOptions } from "./lifecycle.js";

export { ServerLifecycle } from "./lifecycle.js";
export { doctor } from "./doctor.js";
export type { ServerOptions } from "./lifecycle.js";
export type { DoctorResult } from "./doctor.js";

export interface MemantoOptions extends ServerOptions {
  /** Agent id to bind this client to. Created if missing on first call. */
  agentId: string;
  /**
   * Auto-create the agent if it does not exist (default: true).
   * Set to false to require explicit creation.
   */
  autoCreate?: boolean;
}

export interface RememberInput {
  content: string;
  type?: string;
  title?: string;
  confidence?: number;
  tags?: string[];
  source?: string;
  provenance?: string;
}

export interface BatchRememberItem {
  content: string;
  type?: string;
  title?: string;
  confidence?: number;
  tags?: string[];
  source?: string;
  provenance?: string;
}

export interface RecallInput {
  query: string;
  limit?: number;
  minSimilarity?: number;
  type?: string[];
}

export interface AnswerInput {
  question: string;
  limit?: number;
  threshold?: number;
  temperature?: number;
  aiModel?: string;
  kioskMode?: boolean;
}

export interface RecallAsOfInput {
  /** YYYY-MM-DD or ISO 8601 datetime. */
  asOf: string;
  limit?: number;
  type?: string[];
}

export interface RecallChangedSinceInput {
  /** YYYY-MM-DD or ISO 8601 datetime. */
  since: string;
  limit?: number;
  type?: string[];
}

export interface RecallRecentInput {
  limit?: number;
  type?: string[];
}

export interface CreateAgentInput {
  /** Agent pattern (defaults to "support" server-side). */
  pattern?: string;
  description?: string;
}

export interface DailySummaryInput {
  /** YYYY-MM-DD. Defaults to today. */
  date?: string;
  outputPath?: string;
}

export interface ConflictDateInput {
  /** YYYY-MM-DD. Defaults to today. */
  date?: string;
}

export interface ResolveConflictInput {
  conflictIndex: number;
  /** keep_old | keep_new | keep_both | remove_both | manual */
  action: string;
  date?: string;
  manualContent?: string;
  manualType?: string;
}

export interface UploadFileInput {
  /** Absolute or relative path to the file. */
  path: string;
  /** Override the filename sent in the multipart body. */
  filename?: string;
}

export interface ConversationMessage {
  role: string;
  content: string;
}

export interface ExtractMemoriesInput {
  messages: ConversationMessage[];
  /** Return candidates without writing them. Defaults to false. */
  dryRun?: boolean;
  /** 1-100. Defaults to 20 server-side. */
  maxMemories?: number;
  /** Optional model override for extraction. */
  aiModel?: string;
}

interface SessionRecord {
  session_token: string;
  agent_id: string;
  session_id: string;
}

/**
 * Ergonomic Memanto client. Spawns a local memanto server via `uvx` on
 * first use, creates/activates the agent, and forwards calls to the
 * session-scoped REST endpoints.
 */
export class Memanto {
  private readonly lifecycle: ServerLifecycle;
  private readonly agentId: string;
  private readonly autoCreate: boolean;
  private sessionToken: string | null = null;
  private starting: Promise<void> | null = null;

  constructor(opts: MemantoOptions) {
    if (!opts.agentId) throw new Error("Memanto: agentId is required");
    this.agentId = opts.agentId;
    this.autoCreate = opts.autoCreate ?? true;
    this.lifecycle = new ServerLifecycle(opts);
  }

  // ---------------------------------------------------------------------------
  // Memory writes
  // ---------------------------------------------------------------------------

  async remember(input: RememberInput) {
    return this.request("POST", `/api/v2/agents/${this.agentId}/remember`, {
      content: input.content,
      type: input.type,
      title: input.title,
      confidence: input.confidence ?? 0.8,
      tags: input.tags,
      source: input.source ?? "agent",
      provenance: input.provenance ?? "explicit_statement",
    });
  }

  async batchRemember(items: BatchRememberItem[]) {
    return this.request(
      "POST",
      `/api/v2/agents/${this.agentId}/batch-remember`,
      {
        memories: items.map((m) => ({
          content: m.content,
          type: m.type,
          title: m.title,
          confidence: m.confidence ?? 0.8,
          tags: m.tags,
          source: m.source ?? "agent",
          provenance: m.provenance ?? "explicit_statement",
        })),
      },
    );
  }

  async extractMemories(input: ExtractMemoriesInput) {
    return this.request(
      "POST",
      `/api/v2/agents/${this.agentId}/remember/extract`,
      {
        messages: input.messages,
        dry_run: input.dryRun,
        max_memories: input.maxMemories,
        ai_model: input.aiModel,
      },
    );
  }

  async deleteMemory(memoryId: string) {
    return this.request(
      "DELETE",
      `/api/v2/agents/${this.agentId}/memories/${encodeURIComponent(memoryId)}`,
    );
  }

  async uploadFile(input: UploadFileInput) {
    await this.ensureReady();
    const bytes = await readFile(input.path);
    const form = new FormData();
    const blob = new Blob([new Uint8Array(bytes)]);
    form.append("file", blob, input.filename ?? basename(input.path));
    return this.requestMultipart(
      `/api/v2/agents/${this.agentId}/upload-file`,
      form,
    );
  }

  // ---------------------------------------------------------------------------
  // Memory reads
  // ---------------------------------------------------------------------------

  async recall(input: RecallInput) {
    return this.request("POST", `/api/v2/agents/${this.agentId}/recall`, {
      query: input.query,
      limit: input.limit,
      min_similarity: input.minSimilarity,
      type: input.type,
    });
  }

  async recallAsOf(input: RecallAsOfInput) {
    return this.request(
      "POST",
      `/api/v2/agents/${this.agentId}/recall/as-of`,
      { as_of: input.asOf, limit: input.limit, type: input.type },
    );
  }

  async recallChangedSince(input: RecallChangedSinceInput) {
    return this.request(
      "POST",
      `/api/v2/agents/${this.agentId}/recall/changed-since`,
      { since: input.since, limit: input.limit, type: input.type },
    );
  }

  async recallRecent(input: RecallRecentInput = {}) {
    return this.request(
      "POST",
      `/api/v2/agents/${this.agentId}/recall/recent`,
      { limit: input.limit, type: input.type },
    );
  }

  async answer(input: AnswerInput) {
    return this.request("POST", `/api/v2/agents/${this.agentId}/answer`, {
      question: input.question,
      limit: input.limit,
      threshold: input.threshold,
      temperature: input.temperature,
      ai_model: input.aiModel,
      kiosk_mode: input.kioskMode ?? false,
    });
  }

  // ---------------------------------------------------------------------------
  // Analysis (summaries + conflicts)
  // ---------------------------------------------------------------------------

  async dailySummary(input: DailySummaryInput = {}) {
    return this.request(
      "POST",
      `/api/v2/agents/${this.agentId}/daily-summary`,
      { date: input.date, output_path: input.outputPath },
    );
  }

  async generateConflicts(input: ConflictDateInput = {}) {
    return this.request(
      "POST",
      `/api/v2/agents/${this.agentId}/conflicts/generate`,
      { date: input.date },
    );
  }

  async listConflicts(input: ConflictDateInput = {}) {
    const qs = input.date ? `?date=${encodeURIComponent(input.date)}` : "";
    return this.request(
      "GET",
      `/api/v2/agents/${this.agentId}/conflicts${qs}`,
    );
  }

  async resolveConflict(input: ResolveConflictInput) {
    return this.request(
      "POST",
      `/api/v2/agents/${this.agentId}/conflicts/resolve`,
      {
        conflict_index: input.conflictIndex,
        action: input.action,
        date: input.date,
        manual_content: input.manualContent,
        manual_type: input.manualType,
      },
    );
  }

  // ---------------------------------------------------------------------------
  // Agent + session lifecycle
  // ---------------------------------------------------------------------------

  async listAgents() {
    return this.request("GET", `/api/v2/agents`, undefined, {
      requireSession: false,
    });
  }

  async getAgent() {
    return this.request("GET", `/api/v2/agents/${this.agentId}`, undefined, {
      requireSession: false,
    });
  }

  async createAgent(input: CreateAgentInput = {}) {
    await this.lifecycle.start();
    const baseUrl = this.lifecycle.baseUrl;
    const res = await fetch(`${baseUrl}/api/v2/agents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent_id: this.agentId,
        pattern: input.pattern,
        description: input.description,
      }),
    });
    if (!res.ok) throw await asError(res, "Failed to create agent");
    return (await res.json()) as unknown;
  }

  /** Delete the bound agent and clear any cached session for it. */
  async deleteAgent() {
    const result = await this.request(
      "DELETE",
      `/api/v2/agents/${this.agentId}`,
      undefined,
      { requireSession: false },
    );
    this.sessionToken = null;
    this.starting = null;
    return result;
  }

  async deactivate() {
    const result = await this.request(
      "POST",
      `/api/v2/agents/${this.agentId}/deactivate`,
    );
    this.sessionToken = null;
    this.starting = null;
    return result;
  }

  async status() {
    return this.request("GET", `/api/v2/status`);
  }

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  async close(): Promise<void> {
    this.sessionToken = null;
    this.starting = null;
    await this.lifecycle.stop();
  }

  // ---------------------------------------------------------------------------
  // Internals
  // ---------------------------------------------------------------------------

  private async ensureReady(): Promise<void> {
    if (this.sessionToken) return;
    if (!this.starting) this.starting = this.bootstrap();
    try {
      await this.starting;
    } catch (e) {
      this.starting = null;
      throw e;
    }
  }

  private async bootstrap(): Promise<void> {
    await this.lifecycle.start();
    if (this.autoCreate) await this.createAgentIfMissing();
    await this.activate();
  }

  private async createAgentIfMissing(): Promise<void> {
    const baseUrl = this.lifecycle.baseUrl;
    const res = await fetch(`${baseUrl}/api/v2/agents/${this.agentId}`);
    if (res.ok) return;
    if (res.status !== 404) {
      throw await asError(res, "Failed to look up agent");
    }
    const create = await fetch(`${baseUrl}/api/v2/agents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: this.agentId }),
    });
    if (!create.ok && create.status !== 409) {
      throw await asError(create, "Failed to create agent");
    }
  }

  private async activate(): Promise<void> {
    const baseUrl = this.lifecycle.baseUrl;
    const res = await fetch(`${baseUrl}/api/v2/agents/${this.agentId}/activate`, {
      method: "POST",
    });
    if (!res.ok) throw await asError(res, "Failed to activate agent");
    const session = (await res.json()) as SessionRecord;
    this.sessionToken = session.session_token;
  }

  private async request<T = unknown>(
    method: string,
    path: string,
    body?: unknown,
    opts: { requireSession?: boolean } = {},
  ): Promise<T> {
    const requireSession = opts.requireSession ?? true;
    if (requireSession) {
      await this.ensureReady();
    } else {
      await this.lifecycle.start();
    }
    const baseUrl = this.lifecycle.baseUrl;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (requireSession) {
      headers["X-Session-Token"] = this.sessionToken ?? "";
    }
    const res = await fetch(`${baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) throw await asError(res, `${method} ${path} failed`);
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  private async requestMultipart<T = unknown>(
    path: string,
    form: FormData,
  ): Promise<T> {
    await this.ensureReady();
    const baseUrl = this.lifecycle.baseUrl;
    const res = await fetch(`${baseUrl}${path}`, {
      method: "POST",
      headers: { "X-Session-Token": this.sessionToken ?? "" },
      body: form,
    });
    if (!res.ok) throw await asError(res, `POST ${path} failed`);
    return (await res.json()) as T;
  }
}

async function asError(res: Response, prefix: string): Promise<Error> {
  let detail = "";
  try {
    const text = await res.text();
    try {
      const body = JSON.parse(text) as { detail?: unknown; message?: unknown };
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body);
    } catch {
      detail = text;
    }
  } catch {
    detail = "";
  }
  return new Error(`${prefix} (${res.status}): ${detail}`);
}
