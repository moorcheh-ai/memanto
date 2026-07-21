import { Client } from '../src/client';

describe('Client', () => {
  let client: Client;

  beforeEach(() => {
    client = new Client();
  });

  it('should retry the request once with a refreshed token on 401', async () => {
    const mockFetch = jest.fn()
      .mockResolvedValueOnce({ status: 401 })
      .mockResolvedValueOnce({ status: 200 });

    global.fetch = mockFetch;

    jest.spyOn(client['session'], 'getToken').mockResolvedValue('stale-token');
    jest.spyOn(client['session'], 'refresh').mockResolvedValue(undefined);

    const response = await client.request('/api/data');

    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(response.status).toBe(200);
  });

  it('should invalidate the session and throw error on second 401', async () => {
    const mockFetch = jest.fn()
      .mockResolvedValueOnce({ status: 401 })
      .mockResolvedValueOnce({ status: 401 });

    global.fetch = mockFetch;

    jest.spyOn(client['session'], 'getToken').mockResolvedValue('stale-token');
    jest.spyOn(client['session'], 'invalidate').mockImplementation(() => {});

    await expect(client.request('/api/data')).rejects.toThrow();
    expect(client['session'].invalidate).toHaveBeenCalled();
  });

  it('should handle concurrent requests with the same stale token', async () => {
    const mockFetch = jest.fn()
      .mockResolvedValueOnce({ status: 401 })
      .mockResolvedValueOnce({ status: 200 });

    global.fetch = mockFetch;

    jest.spyOn(client['session'], 'getToken').mockResolvedValue('stale-token');
    jest.spyOn(client['session'], 'refresh').mockResolvedValue(undefined);

    const promises = [
      client.request('/api/data'),
      client.request('/api/data'),
      client.request('/api/data'),
    ];

    const responses = await Promise.all(promises);

    expect(mockFetch).toHaveBeenCalledTimes(4); // Initial 3 requests + 1 retry
    responses.forEach(response => {
      expect(response.status).toBe(200);
    });
  });
});