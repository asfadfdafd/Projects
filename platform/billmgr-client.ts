/**
 * BILLmanager 6 client — the only place that knows how 24saas's cabinet is
 * spoken to. Everything above it sees plain objects.
 *
 * Three properties the rest of the adapter depends on:
 *  - a session is re-acquired transparently when it expires (one hour idle);
 *  - an error arrives in the body, not in the HTTP status, so it is turned
 *    into a thrown BillmgrError here and never leaks as a "successful" doc;
 *  - a transport failure is distinguishable from a rejection, because the
 *    orchestrator retries one and must not retry the other blindly.
 */

export class BillmgrError extends Error {
  constructor(
    readonly type: string,
    message: string,
    readonly func: string,
  ) {
    super(message);
    this.name = 'BillmgrError';
  }

  /** Wrong credentials, expired session, insufficient access level. */
  get isAuth(): boolean {
    return ['auth', 'access', 'authfail', 'badauth'].includes(this.type);
  }
}

export class BillmgrTransportError extends Error {
  constructor(message: string, readonly cause?: unknown) {
    super(message);
    this.name = 'BillmgrTransportError';
  }
}

export interface BillmgrConfig {
  /** e.g. https://cabinet.24saas.kz/billmgr */
  url: string;
  username: string;
  password: string;
  timeoutMs?: number;
}

type Params = Record<string, string | number | undefined>;

export class BillmgrClient {
  private session: string | null = null;

  constructor(private readonly config: BillmgrConfig) {}

  /** A read. Never applies anything — BILLmanager needs sok=ok for that. */
  read<T = BillmgrDoc>(func: string, params: Params = {}): Promise<T> {
    return this.request<T>(func, params) as Promise<T>;
  }

  /** A write. sok=ok is added here so no call site can forget it. */
  write<T = BillmgrDoc>(func: string, params: Params = {}): Promise<T> {
    return this.request<T>(func, { ...params, sok: 'ok' }) as Promise<T>;
  }

  private async request<T>(func: string, params: Params, retriedAuth = false): Promise<T> {
    const auth = await this.ensureSession();
    const doc = await this.post({ ...params, func, auth });
    const error = extractError(doc);
    if (error) {
      const err = new BillmgrError(error.type, error.message, func);
      // An expired session looks exactly like a rejection; retry once.
      if (err.isAuth && !retriedAuth) {
        this.session = null;
        return this.request<T>(func, params, true);
      }
      throw err;
    }
    return doc as T;
  }

  private async ensureSession(): Promise<string> {
    if (this.session) return this.session;
    const doc = await this.post({
      func: 'auth',
      username: this.config.username,
      password: this.config.password,
    });
    const error = extractError(doc);
    if (error) throw new BillmgrError(error.type, error.message, 'auth');
    const id = valueOf(doc?.doc?.auth) ?? (doc?.doc?.auth as { $id?: string } | undefined)?.$id;
    if (!id) throw new BillmgrError('auth', 'no session id in auth response', 'auth');
    this.session = String(id);
    return this.session;
  }

  private async post(params: Params): Promise<BillmgrDoc> {
    const body = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) body.set(k, String(v));
    }
    body.set('out', 'json');

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.config.timeoutMs ?? 30_000);
    try {
      const res = await fetch(this.config.url, {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body,
        signal: controller.signal,
      });
      const text = await res.text();
      try {
        return JSON.parse(text) as BillmgrDoc;
      } catch {
        throw new BillmgrTransportError(
          `non-JSON response (HTTP ${res.status}): ${text.slice(0, 200)}`,
        );
      }
    } catch (cause) {
      if (cause instanceof BillmgrTransportError) throw cause;
      throw new BillmgrTransportError(`request to BILLmanager failed`, cause);
    } finally {
      clearTimeout(timer);
    }
  }
}

// --- response shapes -------------------------------------------------------
// BILLmanager wraps scalars as { "$": "value" } in JSON output, and a list of
// one element is an object rather than an array. Both are normalised here so
// no call site has to remember it.

export interface BillmgrDoc {
  doc?: Record<string, unknown>;
  [key: string]: unknown;
}

export function valueOf(node: unknown): string | undefined {
  if (node == null) return undefined;
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (typeof node === 'object' && '$' in (node as Record<string, unknown>)) {
    const v = (node as { $: unknown }).$;
    return v == null ? undefined : String(v);
  }
  return undefined;
}

export function rowsOf(doc: BillmgrDoc): Array<Record<string, string | undefined>> {
  const elem = (doc.doc?.elem ?? doc.elem) as unknown;
  if (!elem) return [];
  const list = Array.isArray(elem) ? elem : [elem];
  return list.map((row) => {
    const flat: Record<string, string | undefined> = {};
    for (const [key, node] of Object.entries(row as Record<string, unknown>)) {
      flat[key] = valueOf(node);
    }
    return flat;
  });
}

function extractError(doc: BillmgrDoc): { type: string; message: string } | null {
  const raw = (doc?.doc?.error ?? doc?.error) as Record<string, unknown> | undefined;
  if (!raw) return null;
  const type = String(raw.$type ?? raw.type ?? 'unknown');
  const message = valueOf(raw.msg) ?? JSON.stringify(raw).slice(0, 300);
  return { type, message };
}
