import { Session } from './session';

export class Client {
  private session: Session;

  constructor() {
    this.session = new Session(this);
  }

  async activateSession(): Promise<string> {
    // Implementation for activating a new session
    // This would make an API call to your backend to get a new token
    // For example:
    // const response = await fetch('/api/activate');
    // return response.json().token;
    throw new Error('Not implemented');
  }

  async request(endpoint: string, options: RequestOptions = {}): Promise<Response> {
    try {
      const token = await this.session.getToken();
      const response = await fetch(endpoint, {
        ...options,
        headers: {
          ...options.headers,
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.status === 401) {
        await this.session.refresh();
        const newToken = await this.session.getToken();
        return fetch(endpoint, {
          ...options,
          headers: {
            ...options.headers,
            'Authorization': `Bearer ${newToken}`,
          },
        });
      }

      return response;
    } catch (error) {
      if (error instanceof Error && error.message.includes('401')) {
        this.session.invalidate();
        throw error;
      }
      throw error;
    }
  }
}

interface RequestOptions extends RequestInit {
  // Add any additional options you need
}