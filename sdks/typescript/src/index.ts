import { randomUUID } from "node:crypto";
import { openAsBlob } from "node:fs";
import { stat } from "node:fs/promises";
import { basename } from "node:path";

import { ServerLifecycle, type ServerOptions } from "./lifecycle.js";

export { ServerLifecycle } from "./lifecycle.js";
export { doctor } from "./doctor.js";
export type { ServerOptions } from "./lifecycle.js";
export type { DoctorResult } from "./doctor.js";

/** Default public gateway for Memanto Cloud (`MEMANTO_API_KEY`). */
export const DEFAULT_MEMANTO_API_URL =
  "https://memanto-saas-public-gw-33wzz25k.ue.gateway.dev";

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
  /** Only return memories carrying all of these tags. */
  tags?: string[];
  /** Slug of the AI tool making this call (e.g. "cursor", "copilot"). */
  source?: string;
}

export interface AnswerInput {
  question: string;
  limit?: number;
  threshold?: number;
  temperature?: number;
  aiModel?: string;
  kioskMode?: boolean;
  /** Slug of the AI tool making this call (e.g. "cursor", "copilot"). */
  source?: string;
}

export interface RecallAsOfInput {
  /** YYYY-MM-DD or ISO 8601 datetime. */
  asOf: string;
  limit?: number;
  type?: string[];
  /** Slug of the AI tool making this call (e.g. "cursor", "copilot"). */
  source?: string;
}

export interface RecallChangedSinceInput {
  /** YYYY-MM-DD or ISO 8601 datetime. */
  since: string;
  limit?: number;
  type?: string[];
  /** Slug of the AI tool making this call (e.g. "cursor", "copilot"). */
  source?: string;
}

export interface RecallRecentInput {
  limit?: number;
  type?: string[];
  /** Slug of the AI tool making this call (e.g. "cursor", "copilot"). */
  source?: string;
}

export interface CreateAgentInput {
  /** Agent pattern (defaults to "support" server-side). */
  pattern?: string;
  description?: string;
}

export interface DeleteAgentInput {
  /** Also permanently delete the agent's memories in Moorcheh. */
  deleteMemories?: boolean;
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
  /** Slug of the AI tool making this call (e.g. "cursor", "copilot"). */
  source?: string;
}

interface SessionRecord {
  session_token: string;
  agent_id: string;
  session_id: string;
}

interface CloudUploadResponse {
  upload_url: string;
  content_type?: string;
  file_id?: string;
  job_id?: string;
  file_name?: string;
}

function plainCloudMemory(memory: unknown): unknown {
  if (!memory || typeof memory !== "object") return memory;
  const rec = memory as Record<string, unknown>;
  if (typeof rec.content !== "string") return memory;
  const sepIdx = rec.content.indexOf("\n\n");
  if (sepIdx === -1) return memory;
  const head = rec.content.slice(0, sepIdx);
  let body = rec.content.slice(sepIdx + 2);
  const headerMatch = /^\[([A-Za-z]+)\] /.exec(head);
  const memType = typeof rec.type === "string" ? rec.type : "";
  if (!headerMatch || headerMatch[1].toLowerCase() !== memType.toLowerCase()) {
    return memory;
  }
  const tags = Array.isArray(rec.tags)
    ? rec.tags.map((t) => String(t).trim()).filter(Boolean)
    : [];
  if (tags.length > 0) {
    const marker = "\n\nTags: ";
    const footerIdx = body.lastIndexOf(marker);
    if (footerIdx !== -1) {
      const footerTags = body
        .slice(footerIdx + marker.length)
        .split(",")
        .map((t) => t.trim());
      if (
        footerTags.length === tags.length &&
        footerTags.every((t, i) => t === tags[i])
      ) {
        body = body.slice(0, footerIdx);
      }
    }
  }
  return { ...rec, content: body };
}

function normalizeCloudRecallResult<T>(result: T): T {
  if (!result || typeof result !== "object") return result;
  const rec = result as Record<string, unknown>;
  if (!Array.isArray(rec.memories)) return result;
  return {
    ...rec,
    memories: rec.memories.map(plainCloudMemory),
  } as T;
}

/**
 * Ergonomic Memanto client. Connects directly to Memanto Cloud when configured
 * with a Memanto Cloud API key (`mk_...` or `MEMANTO_API_KEY`), or falls back
 * to spawning a local memanto server via `uvx` (`MOORCHEH_API_KEY` / on-prem).
 */
export class Memanto {
  private readonly lifecycle: ServerLifecycle;
  private readonly agentId: string;
  private readonly encodedAgentId: string;
  private readonly autoCreate: boolean;
  private readonly isCloud: boolean;
  private readonly agentsRootPath: string;
  private readonly agentPath: string;
  // Memanto Cloud requires X-Api-Key on all requests; a local server bound
  // beyond loopback requires it for agent create/activate.
  private readonly authHeaders: Record<string, string>;
  private sessionToken: string | null = null;
  private agentEnsured = false;
  private starting: Promise<void> | null = null;

  constructor(opts: MemantoOptions) {
    if (!opts.agentId) throw new Error("Memanto: agentId is required");
    this.agentId = opts.agentId;
    this.encodedAgentId = encodeURIComponent(opts.agentId);
    this.autoCreate = opts.autoCreate ?? true;

    const explicitKey = opts.apiKey?.trim() || undefined;
    const envMemantoKey = process.env.MEMANTO_API_KEY?.trim() || undefined;
    const envMoorchehKey = process.env.MOORCHEH_API_KEY?.trim() || undefined;
    const envCloudUrl = process.env.MEMANTO_API_URL?.trim() || undefined;

    const hasLocalServerOpts = Boolean(
      opts.baseUrl || opts.uvxPath || opts.host || opts.port || opts.packageSpec,
    );
    let resolvedApiKey = explicitKey;
    if (explicitKey) {
      this.isCloud =
        explicitKey.startsWith("mk_") ||
        (Boolean(envMemantoKey) && explicitKey === envMemantoKey);
    } else if (!hasLocalServerOpts && envMemantoKey) {
      this.isCloud = true;
      resolvedApiKey = envMemantoKey;
    } else if (!opts.baseUrl && envMoorchehKey) {
      this.isCloud = false;
      resolvedApiKey = envMoorchehKey;
    } else {
      this.isCloud = false;
    }

    this.agentsRootPath = this.isCloud ? "/agents" : "/api/v2/agents";
    this.agentPath = `${this.agentsRootPath}/${this.encodedAgentId}`;
    this.authHeaders = resolvedApiKey ? { "X-Api-Key": resolvedApiKey } : {};
    const effectiveBaseUrl = this.isCloud
      ? opts.baseUrl?.trim() || envCloudUrl || DEFAULT_MEMANTO_API_URL
      : opts.baseUrl;
    this.lifecycle = new ServerLifecycle({
      ...opts,
      apiKey: resolvedApiKey,
      baseUrl: effectiveBaseUrl,
    });
  }

  // ---------------------------------------------------------------------------
  // Memory writes
  // ---------------------------------------------------------------------------

  async remember(input: RememberInput) {
    return this.request("POST", `${this.agentPath}/remember`, {
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
      `${this.agentPath}/batch-remember`,
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
      `${this.agentPath}/remember/extract`,
      {
        messages: input.messages,
        dry_run: input.dryRun,
        max_memories: input.maxMemories,
        ai_model: input.aiModel,
        source: input.source,
      },
    );
  }

  async deleteMemory(memoryId: string) {
    return this.request(
      "DELETE",
      `${this.agentPath}/memories/${encodeURIComponent(memoryId)}`,
    );
  }

  async uploadFile(input: UploadFileInput) {
    await this.ensureReady();
    const filename = input.filename ?? basename(input.path);
    if (this.isCloud) {
      return this.requestCloudFileUpload(input.path, filename);
    }
    return this.requestFileUpload(
      `${this.agentPath}/upload-file`,
      input.path,
      filename,
    );
  }

  // ---------------------------------------------------------------------------
  // Memory reads
  // ---------------------------------------------------------------------------

  async recall(input: RecallInput) {
    const res = await this.request("POST", `${this.agentPath}/recall`, {
      query: input.query,
      limit: input.limit,
      min_similarity: input.minSimilarity,
      type: input.type,
      tags: input.tags,
      source: input.source,
    });
    return this.isCloud ? normalizeCloudRecallResult(res) : res;
  }

  async recallAsOf(input: RecallAsOfInput) {
    const res = await this.request(
      "POST",
      `${this.agentPath}/recall/as-of`,
      {
        as_of: input.asOf,
        limit: input.limit,
        type: input.type,
        source: input.source,
      },
    );
    return this.isCloud ? normalizeCloudRecallResult(res) : res;
  }

  async recallChangedSince(input: RecallChangedSinceInput) {
    const res = await this.request(
      "POST",
      `${this.agentPath}/recall/changed-since`,
      {
        since: input.since,
        limit: input.limit,
        type: input.type,
        source: input.source,
      },
    );
    return this.isCloud ? normalizeCloudRecallResult(res) : res;
  }

  async recallRecent(input: RecallRecentInput = {}) {
    const res = await this.request(
      "POST",
      `${this.agentPath}/recall/recent`,
      { limit: input.limit, type: input.type, source: input.source },
    );
    return this.isCloud ? normalizeCloudRecallResult(res) : res;
  }

  async answer(input: AnswerInput) {
    return this.request("POST", `${this.agentPath}/answer`, {
      question: input.question,
      limit: input.limit,
      threshold: input.threshold,
      temperature: input.temperature,
      ai_model: input.aiModel,
      kiosk_mode: input.kioskMode ?? false,
      source: input.source,
    });
  }

  // ---------------------------------------------------------------------------
  // Analysis (summaries + conflicts)
  // ---------------------------------------------------------------------------

  async dailySummary(input: DailySummaryInput = {}) {
    return this.request(
      "POST",
      `${this.agentPath}/daily-summary`,
      { date: input.date, output_path: input.outputPath },
    );
  }

  async generateConflicts(input: ConflictDateInput = {}) {
    return this.request(
      "POST",
      `${this.agentPath}/conflicts/generate`,
      { date: input.date },
    );
  }

  async listConflicts(input: ConflictDateInput = {}) {
    const qs = input.date ? `?date=${encodeURIComponent(input.date)}` : "";
    return this.request(
      "GET",
      `${this.agentPath}/conflicts${qs}`,
    );
  }

  async resolveConflict(input: ResolveConflictInput) {
    return this.request(
      "POST",
      `${this.agentPath}/conflicts/resolve`,
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
    return this.request("GET", this.agentsRootPath, undefined, {
      requireSession: false,
    });
  }

  async getAgent() {
    return this.request("GET", this.agentPath, undefined, {
      requireSession: false,
    });
  }

  async createAgent(input: CreateAgentInput = {}) {
    await this.lifecycle.start();
    const baseUrl = this.lifecycle.baseUrl;
    const res = await fetch(`${baseUrl}${this.agentsRootPath}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.authHeaders },
      body: JSON.stringify({
        agent_id: this.agentId,
        pattern: input.pattern,
        description: input.description,
      }),
    });
    if (!res.ok) throw await asError(res, "Failed to create agent");
    return (await res.json()) as unknown;
  }

  /**
   * Delete the bound agent and clear any cached session for it.
   *
   * On Memanto local, memories stay in Moorcheh unless `deleteMemories` is true.
   * On Memanto Cloud, deleting an agent always deletes its memories.
   */
  async deleteAgent(input: DeleteAgentInput = {}) {
    const query =
      !this.isCloud && input.deleteMemories ? "?delete-backup-too=true" : "";
    const result = await this.request(
      "DELETE",
      `${this.agentPath}${query}`,
      undefined,
      { requireSession: false },
    );
    this.sessionToken = null;
    this.agentEnsured = false;
    this.starting = null;
    return result;
  }

  async deactivate() {
    if (this.isCloud) {
      this.sessionToken = null;
      this.agentEnsured = false;
      this.starting = null;
      return { agent_id: this.agentId, status: "deactivated" };
    }
    const result = await this.request(
      "POST",
      `${this.agentPath}/deactivate`,
    );
    this.sessionToken = null;
    this.starting = null;
    return result;
  }

  async status() {
    return this.request(
      "GET",
      this.isCloud ? "/me" : "/api/v2/status",
      undefined,
      { requireSession: false },
    );
  }

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  async close(): Promise<void> {
    this.sessionToken = null;
    this.agentEnsured = false;
    this.starting = null;
    await this.lifecycle.stop();
  }

  // ---------------------------------------------------------------------------
  // Internals
  // ---------------------------------------------------------------------------

  private async ensureReady(): Promise<void> {
    if (this.isCloud ? this.agentEnsured : Boolean(this.sessionToken)) return;
    if (!this.starting) this.starting = this.bootstrap();
    const starting = this.starting;
    try {
      await starting;
    } finally {
      if (this.starting === starting) this.starting = null;
    }
  }

  private async refreshExpiredSession(staleToken: string | null): Promise<void> {
    // Another request may already have refreshed the shared client while this
    // request was waiting for its 401 response.
    if (this.sessionToken && this.sessionToken !== staleToken) return;
    this.sessionToken = null;
    if (!this.starting) this.starting = this.reactivate();
    const starting = this.starting;
    try {
      await starting;
    } finally {
      if (this.starting === starting) this.starting = null;
    }
  }

  private async bootstrap(): Promise<void> {
    await this.lifecycle.start();
    if (this.autoCreate) await this.createAgentIfMissing();
    if (this.isCloud) {
      this.agentEnsured = true;
      return;
    }
    await this.activate();
  }

  private async reactivate(): Promise<void> {
    await this.lifecycle.start();
    await this.activate();
  }

  private async createAgentIfMissing(): Promise<void> {
    const baseUrl = this.lifecycle.baseUrl;
    const res = await fetch(`${baseUrl}${this.agentPath}`, {
      headers: this.authHeaders,
    });
    if (res.ok) return;
    if (res.status !== 404) {
      throw await asError(res, "Failed to look up agent");
    }
    const create = await fetch(`${baseUrl}${this.agentsRootPath}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.authHeaders },
      body: JSON.stringify({ agent_id: this.agentId }),
    });
    if (!create.ok && create.status !== 409) {
      throw await asError(create, "Failed to create agent");
    }
  }

  private async activate(): Promise<void> {
    const baseUrl = this.lifecycle.baseUrl;
    const res = await fetch(`${baseUrl}${this.agentPath}/activate`, {
      method: "POST",
      headers: this.authHeaders,
    });
    if (!res.ok) throw await asError(res, "Failed to activate agent");
    const session = (await res.json()) as SessionRecord;
    this.sessionToken = session.session_token;
  }

  private async sendWithSessionRetry(
    send: () => Promise<Response>,
    headers: Record<string, string>,
    retryOn401: boolean,
  ): Promise<Response> {
    const staleToken = this.sessionToken;
    let res = await send();
    if (!this.isCloud && retryOn401 && res.status === 401) {
      await this.refreshExpiredSession(staleToken);
      headers["X-Session-Token"] = this.sessionToken ?? "";
      res = await send();
    }
    return res;
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
      ...this.authHeaders,
    };
    if (requireSession && !this.isCloud) {
      headers["X-Session-Token"] = this.sessionToken ?? "";
    }
    const serializedBody = body === undefined ? undefined : JSON.stringify(body);
    const send = () =>
      fetch(`${baseUrl}${path}`, { method, headers, body: serializedBody });
    const res = await this.sendWithSessionRetry(send, headers, requireSession);
    if (!res.ok) throw await asError(res, `${method} ${path} failed`);
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  private async requestCloudFileUpload<T = unknown>(
    filePath: string,
    filename: string,
  ): Promise<T> {
    const fileStats = await stat(filePath);
    if (!fileStats.isFile()) {
      throw new Error(`Upload path is not a file: ${filePath}`);
    }
    const created = await this.request<CloudUploadResponse>(
      "POST",
      `${this.agentPath}/files`,
      { file_name: filename, size_bytes: fileStats.size },
    );
    const fileBlob = await openAsBlob(filePath);
    const putRes = await fetch(created.upload_url, {
      method: "PUT",
      headers: {
        "Content-Type": created.content_type || "application/octet-stream",
      },
      body: fileBlob,
    });
    if (!putRes.ok) {
      throw new Error(`File upload to storage failed (HTTP ${putRes.status})`);
    }
    return {
      agent_id: this.agentId,
      namespace: this.agentId,
      success: true,
      status: "queued",
      file_name: created.file_name ?? filename,
      file_size: fileStats.size,
      file_id: created.file_id,
      job_id: created.job_id,
    } as T;
  }

  private async requestFileUpload<T = unknown>(
    path: string,
    filePath: string,
    filename: string,
  ): Promise<T> {
    await this.ensureReady();
    const baseUrl = this.lifecycle.baseUrl;
    const fileStats = await stat(filePath);
    if (!fileStats.isFile()) {
      throw new Error(`Upload path is not a file: ${filePath}`);
    }
    const headers: Record<string, string> = {
      ...this.authHeaders,
      "X-Session-Token": this.sessionToken ?? "",
    };
    const send = async () => {
      const formData = new FormData();
      const fileBlob = await openAsBlob(filePath);
      formData.set("file", fileBlob, filename);

      return fetch(`${baseUrl}${path}`, {
        method: "POST",
        headers,
        body: formData,
      });
    };
    const res = await this.sendWithSessionRetry(send, headers, true);
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
