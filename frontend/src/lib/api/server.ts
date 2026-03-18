import { env } from '$env/dynamic/private';

/**
 * Build an internal API URL for server-side fetches.
 * In K8s, API_INTERNAL_URL points directly to api-gateway:8000,
 * bypassing the ingress (no TLS, no rewrite needed).
 * Falls back to /api (relative, resolved via ORIGIN).
 */
export function apiUrl(path: string): string {
  const base = env.API_INTERNAL_URL;
  if (base) {
    // Internal: go directly to api-gateway, no /api prefix needed
    return `${base}${path}`;
  }
  // External: go through ingress which rewrites /api/* → /*
  return `/api${path}`;
}
