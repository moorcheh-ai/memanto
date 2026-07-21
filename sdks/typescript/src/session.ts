import { Client } from './client';

export class Session {
  private token: string | null = null;
  private isRefreshing = false;
  private refreshPromise: Promise<void> | null = null;

  constructor(private client: Client) {}

  async ensureReady(): Promise<void> {
    if (!this.token) {
      await this.activate();
    }
  }

  async activate(): Promise<void> {
    this.token = await this.client.activateSession();
  }

  async getToken(): Promise<string> {
    await this.ensureReady();
    return this.token!;
  }

  async refresh(): Promise<void> {
    if (this.isRefreshing) {
      if (this.refreshPromise) {
        await this.refreshPromise;
      }
      return;
    }

    this.isRefreshing = true;
    this.refreshPromise = (async () => {
      try {
        this.token = await this.client.activateSession();
      } finally {
        this.isRefreshing = false;
        this.refreshPromise = null;
      }
    })();

    await this.refreshPromise;
  }

  invalidate(): void {
    this.token = null;
  }
}