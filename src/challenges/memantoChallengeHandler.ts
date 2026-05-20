export interface MemantoMemory {
  id: string;
  content: string;
  relevanceScore?: number;
  timestamp: string;
}

export interface SkillInteractionSummary {
  skillName: string;
  input: string;
  output: string;
  durationMs: number;
  success: boolean;
  // Additional context like file paths, architectural choices, etc., can be added here.
  context?: Record<string, unknown>;
}

export class MemantoClient {
  private static instance: MemantoClient | null = null;
  private apiKey: string | null = null;
  private readonly baseUrl: string = 'https://api.moorcheh.ai/memanto'; // Assumed API endpoint

  private constructor() {} // Enforce singleton pattern

  /**
   * Initializes the MemantoClient with the necessary API key.
   * This method acts as the "Global Memory Hook" in the skills execution lifecycle,
   * ensuring Memanto is ready to be used.
   * @param apiKey The Moorcheh API key.
   * @returns The singleton instance of MemantoClient.
   * @throws Error if the API key is null, empty, or invalid.
   */
  public static init(apiKey: string): MemantoClient {
    if (!apiKey || apiKey.trim().length === 0) {
      throw new Error("MemantoClient: Moorcheh API key is required for initialization.");
    }
    if (!MemantoClient.instance) {
      MemantoClient.instance = new MemantoClient();
    }
    MemantoClient.instance.apiKey = apiKey;
    return MemantoClient.instance;
  }

  /**
   * Retrieves the singleton instance of MemantoClient.
   * @returns The initialized MemantoClient instance.
   * @throws Error if MemantoClient has not been initialized with an API key.
   */
  public static getInstance(): MemantoClient {
    if (!MemantoClient.instance || !MemantoClient.instance.apiKey) {
      throw new Error("MemantoClient: Client not initialized. Call MemantoClient.init() with an API key first.");
    }
    return MemantoClient.instance;
  }

  /**
   * Sends a summary of a completed skill interaction to Memanto for active extraction.
   * Memanto's backend LLM will process this summary to update the developer's "Engineering Profile",
   * storing architectural choices, codebase quirks, and coding preferences.
   * This directly addresses the "Active Extraction" guideline.
   * @param summary The SkillInteractionSummary object containing details of the completed skill.
   * @returns A Promise that resolves when the extraction request has been successfully sent.
   * @throws Error if the API call fails or the client is not initialized.
   */
  public async recordSkillInteraction(summary: SkillInteractionSummary): Promise<void> {
    if (!this.apiKey) {
      throw new Error("MemantoClient: API key not set. Initialize client with MemantoClient.init() first.");
    }

    try {
      const response = await fetch(`${this.baseUrl}/extract-memory`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.apiKey}`,
        },
        body: JSON.stringify(summary),
      });

      if (!response.ok) {
        let errorDetails = response.statusText;
        try {
          const errorJson = await response.json();
          errorDetails = errorJson.message || JSON.stringify(errorJson);
        } catch {
          // Ignore JSON parsing errors if response is not JSON
        }
        throw new Error(`Memanto API Error (recordSkillInteraction): ${response.status} - ${errorDetails}`);
      }
      // Implicitly, a successful 2xx response means the interaction summary was accepted.
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      throw new Error(`MemantoClient: Failed to record skill interaction: ${errorMessage}`);
    }
  }

  /**
   * Queries Memanto for memories relevant to the current file path or task.
   * These memories are intended to be dynamically injected as a concise system constraint
   * into subsequent skill prompts, eliminating repeated instructions.
   * This implements the "Dynamic Injection" guideline.
   * @param contextIdentifier A string identifying the current context (e.g., file path, task name, project ID).
   * @param limit The maximum number of relevant memories to retrieve (default: 5).
   * @returns A Promise that resolves to an array of MemantoMemory objects. Returns an empty array if no relevant memories are found.
   * @throws Error if the API call fails, the client is not initialized, or the contextIdentifier is invalid.
   */
  public async getRelevantMemories(contextIdentifier: string, limit: number = 5): Promise<MemantoMemory[]> {
    if (!this.apiKey) {
      throw new Error("MemantoClient: API key not set. Initialize client with MemantoClient.init() first.");
    }
    if (!contextIdentifier || contextIdentifier.trim().length === 0) {
      throw new Error("MemantoClient: 'contextIdentifier' cannot be empty or null for retrieving memories.");
    }
    if (limit <= 0) {
      throw new Error("MemantoClient: 'limit' for memories must be a positive number.");
    }

    try {
      const queryParams = new URLSearchParams({
        context: contextIdentifier,
        limit: String(limit),
      }).toString();

      const response = await fetch(`${this.baseUrl}/retrieve-memories?${queryParams}`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
        },
      });

      if (!response.ok) {
        let errorDetails = response.statusText;
        try {
          const errorJson = await response.json();
          errorDetails = errorJson.message || JSON.stringify(errorJson);
        } catch {
          // Ignore JSON parsing errors
        }
        throw new Error(`Memanto API Error (getRelevantMemories): ${response.status} - ${errorDetails}`);
      }

      const memories: MemantoMemory[] = await response.json();

      // Robust validation of the API response structure to prevent unexpected runtime errors
      if (!Array.isArray(memories) || !memories.every(
          m => typeof m === 'object' && m !== null &&
               typeof m.id === 'string' && m.id.length > 0 &&
               typeof m.content === 'string' && m.content.length > 0
          // relevanceScore and timestamp are optional as per interface
      )) {
        throw new Error("MemantoClient: Received malformed or incomplete memories data from API.");
      }

      return memories;
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      throw new Error(`MemantoClient: Failed to retrieve relevant memories: ${errorMessage}`);
    }
  }

  /**
   * Formats a list of Memanto memories into a concise string suitable for injection
   * as a system constraint into an LLM prompt.
   * @param memories An array of MemantoMemory objects.
   * @returns A formatted string or an empty string if no memories are provided.
   */
  public formatMemoriesAsConstraint(memories: MemantoMemory[]): string {
    if (!memories || memories.length === 0) {
      return "";
    }
    const formattedContent = memories.map(m => `- ${m.content.trim()}`).join('\n');
    return `Past engineering decisions and preferences relevant to this task:\n${formattedContent}\n`;
  }
}