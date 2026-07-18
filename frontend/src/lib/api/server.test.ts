import { afterEach, describe, expect, it, vi } from 'vitest';

async function importServerUrl(apiInternalUrl?: string) {
  vi.resetModules();
  vi.doMock('$env/dynamic/private', () => ({
    env: { API_INTERNAL_URL: apiInternalUrl }
  }));
  return import('./server');
}

afterEach(() => {
  vi.resetModules();
  vi.unmock('$env/dynamic/private');
});

describe('apiUrl', () => {
  it('uses API_INTERNAL_URL when configured', async () => {
    const { apiUrl } = await importServerUrl('http://api-gateway:8000');
    expect(apiUrl('/pods/123')).toBe('http://api-gateway:8000/pods/123');
  });

  it('falls back to the ingress /api prefix when unset', async () => {
    const { apiUrl } = await importServerUrl(undefined);
    expect(apiUrl('/credits/balance')).toBe('/api/credits/balance');
  });
});
