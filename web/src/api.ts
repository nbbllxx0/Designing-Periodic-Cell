// REST + server-sent events client of the amm GUI backend (same origin; Vite proxies /api in development).

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  const body = await r.json();
  if (!r.ok) throw new Error(body?.error ?? `${r.status} ${path}`);
  return body as T;
}

export async function post<T>(path: string, body: unknown = {}): Promise<T> {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
  const out = await r.json();
  if (!r.ok) throw new Error(out?.error ?? `${r.status} ${path}`);
  return out as T;
}

export type ServerEvent = { type: string; [k: string]: any };

/** Subscribe to /api/events; reconnects automatically (EventSource). Returns an unsubscribe function. */
export function subscribe(onEvent: (ev: ServerEvent) => void, onState?: (open: boolean) => void): () => void {
  const es = new EventSource("/api/events");
  es.onmessage = (m) => {
    try {
      onEvent(JSON.parse(m.data));
    } catch {
      /* keepalive or malformed: ignore */
    }
  };
  es.onopen = () => onState?.(true);
  es.onerror = () => onState?.(false);
  return () => es.close();
}
