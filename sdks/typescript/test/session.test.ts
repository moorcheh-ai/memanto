import { Session } from '../src/session';
import { Client } from '../src/client';

describe('Session', () => {
  let client: Client;
  let session: Session;

  beforeEach(() => {
    client = new Client();
    session = new Session(client);
  });

  it('should activate a new session when token is null', async () => {
    jest.spyOn(client, 'activateSession').mockResolvedValue('new-token');
    await session.ensureReady();
    expect(client.activateSession).toHaveBeenCalled();
  });

  it('should not activate a new session when token is not null', async () => {
    jest.spyOn(client, 'activateSession').mockResolvedValue('existing-token');
    await session.activate();
    jest.spyOn(client, 'activateSession').mockClear();

    await session.ensureReady();
    expect(client.activateSession).not.toHaveBeenCalled();
  });

  it('should refresh the session token', async () => {
    jest.spyOn(client, 'activateSession').mockResolvedValue('refreshed-token');
    await session.refresh();
    expect(client.activateSession).toHaveBeenCalled();
  });

  it('should share a single refresh across concurrent requests', async () => {
    const refreshPromise = jest.fn().mockResolvedValue('refreshed-token');
    jest.spyOn(client, 'activateSession').mockImplementation(refreshPromise);

    const promises = [
      session.refresh(),
      session.refresh(),
      session.refresh(),
    ];

    await Promise.all(promises);
    expect(refreshPromise).toHaveBeenCalledTimes(1);
  });

  it('should invalidate the session token', () => {
    session.invalidate();
    // Add assertions to verify the token is invalidated
  });
});