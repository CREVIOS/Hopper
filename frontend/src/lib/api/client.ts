const API_BASE = '/api';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

let isRefreshing = false;

async function request<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
  parse: 'json' | 'blob' | 'none' = 'json'
): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as any) };
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers
  });

  // On 401, attempt a silent token refresh and retry once.
  if (res.status === 401 && retry && !isRefreshing) {
    isRefreshing = true;
    try {
      const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        credentials: 'include'
      });
      if (refreshRes.ok) {
        isRefreshing = false;
        return request<T>(path, options, false, parse);
      }
    } catch {}
    isRefreshing = false;
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
    throw new ApiError(401, 'Session expired');
  }

  if (!res.ok) {
    const text = await res.text();
    let message = text || res.statusText;
    try {
      const json = JSON.parse(text);
      message = json.detail || json.message || message;
    } catch {}
    throw new ApiError(res.status, message);
  }

  if (parse === 'blob') return (await res.blob()) as unknown as T;
  if (parse === 'none' || res.status === 204) return undefined as unknown as T;
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body)
    }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PUT',
      body: body === undefined ? undefined : JSON.stringify(body)
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body === undefined ? undefined : JSON.stringify(body)
    }),
  delete: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'DELETE',
      body: body === undefined ? undefined : JSON.stringify(body)
    }),

  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),

  download: (path: string) => request<Blob>(path, { method: 'GET' }, true, 'blob'),

  sse(path: string, onMessage: (data: unknown) => void): EventSource {
    const source = new EventSource(`${API_BASE}${path}`);
    source.onmessage = (event) => onMessage(JSON.parse(event.data));
    return source;
  }
};
