import type { Handle } from '@sveltejs/kit';

// Apply baseline security headers to every SSR response. The ingress can't
// inject these because the cluster's nginx-ingress admission policy disallows
// `configuration-snippet` / `server-snippet` annotations, and the global
// controller config is outside this repo. Setting them here means hardening
// follows the app deployment instead of needing platform coordination.
export const handle: Handle = async ({ event, resolve }) => {
  const response = await resolve(event);
  if (!response.headers.has('X-Content-Type-Options')) {
    response.headers.set('X-Content-Type-Options', 'nosniff');
  }
  if (!response.headers.has('X-Frame-Options')) {
    response.headers.set('X-Frame-Options', 'DENY');
  }
  if (!response.headers.has('Referrer-Policy')) {
    response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  }
  return response;
};
