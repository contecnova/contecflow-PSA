/**
 * offlineQueue.js — IndexedDB queue for offline time imputations
 *
 * When the user registers time while offline, the entry is stored here.
 * On reconnect (online event or manual sync), pending entries are POSTed
 * to /api/v1/imputations in order and removed from the queue.
 */

// IMPORTANT: a separate DB from biOfflineDb / offlineSync (Dexie).
// They share the 'contecflow_offline' name and bump versions over time,
// which would force this raw-IDB consumer into an unrecoverable VersionError
// once Dexie's version surpasses ours.
const DB_NAME   = 'contecflow_offline_queue';
const DB_VERSION = 1;
const STORE     = 'imputations_queue';

export const MAX_RETRY_ATTEMPTS = 3;

/*
 * Auditoría 22-11-2026 (H4 del 05): la cola no era por persona. Si A imputaba sin
 * conexión, cerraba sesión y entraba B, las horas de A se subían como de B; y tras
 * 3 fallos se borraban en silencio. Ahora:
 *   - cada entrada lleva su dueño (`_dueno_user`, `_dueno_org`), que fija
 *     `AuthContext` con `establecerDuenoDeLaCola` al entrar/salir;
 *   - solo se cuenta y se sube lo del usuario y la empresa actuales (lo de otro
 *     espera a que esa persona vuelva a entrar en este navegador);
 *   - tras MAX_RETRY_ATTEMPTS la entrada no se borra: queda `abandonada`, no se
 *     reintenta y se avisa (evento `offline:imputaciones-abandonadas`).
 * Las entradas antiguas sin dueño no se suben (no se sabe de quién son).
 */
interface Dueno { user_id: string; org_id: string | null }
let _dueno: Dueno | null = null;

/** Quién está trabajando ahora (null al cerrar sesión). */
export function establecerDuenoDeLaCola(dueno: Dueno | null): void {
  _dueno = dueno;
}

interface QueueEntry extends Record<string, unknown> {
  id?: number
  queued_at: string
  synced: boolean
  retries: number
  _dueno_user?: string
  _dueno_org?: string | null
  abandonada?: boolean
}

function esDelDueno(e: QueueEntry): boolean {
  return !!_dueno && e._dueno_user === _dueno.user_id && (e._dueno_org ?? null) === _dueno.org_id;
}

interface SyncResult {
  synced: number
  failed: number
  abandoned: number
}

type ApiLike = { post: (url: string, payload: Record<string, unknown>) => Promise<unknown> }

// ── Open DB ──────────────────────────────────────────────────────────────────

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
        store.createIndex('queued_at', 'queued_at', { unique: false });
      }
    };
    req.onsuccess  = () => resolve(req.result);
    req.onerror    = () => reject(req.error);
  });
}

// ── Queue an imputation for later sync ───────────────────────────────────────

export async function queueImputation(payload: Record<string, unknown>): Promise<number> {
  if (!_dueno) throw new Error('offlineQueue: sin sesión no se encola');
  const db    = await openDB();
  const entry: QueueEntry = { ...payload, queued_at: new Date().toISOString(), synced: false, retries: 0, _dueno_user: _dueno.user_id, _dueno_org: _dueno.org_id };
  return new Promise((resolve, reject) => {
    const tx   = db.transaction(STORE, 'readwrite');
    const req  = tx.objectStore(STORE).add(entry);
    req.onsuccess = () => resolve(Number(req.result));   // returns generated id
    req.onerror   = () => reject(req.error);
  });
}

// ── Count pending entries ─────────────────────────────────────────────────────

export async function pendingCount(): Promise<number> {
  // Solo las del usuario actual que siguen reintentándose.
  return (await getAllPending()).filter(e => !e.abandonada).length;
}

// ── Get all pending entries ───────────────────────────────────────────────────

export async function getAllPending(): Promise<QueueEntry[]> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(((req.result as QueueEntry[]) || []).filter(esDelDueno));
    req.onerror   = () => reject(req.error);
  });
}

// ── Delete a synced entry ─────────────────────────────────────────────────────

async function deleteEntry(id: number) {
  const db = await openDB();
  return new Promise<void>((resolve, reject) => {
    const tx  = db.transaction(STORE, 'readwrite');
    const req = tx.objectStore(STORE).delete(id);
    req.onsuccess = () => resolve(undefined);
    req.onerror   = () => reject(req.error);
  });
}

// ── Update retry count for an entry ──────────────────────────────────────────

async function updateRetries(db: IDBDatabase, id: number, retries: number, abandonada = false) {
  return new Promise<void>((resolve, reject) => {
    const tx  = db.transaction(STORE, 'readwrite');
    const store = tx.objectStore(STORE);
    const getReq = store.get(id);
    getReq.onsuccess = () => {
      const entry = getReq.result as QueueEntry | undefined;
      if (!entry) { resolve(undefined); return; }
      const putReq = store.put({ ...entry, retries, abandonada });
      putReq.onsuccess = () => resolve(undefined);
      putReq.onerror   = () => reject(putReq.error);
    };
    getReq.onerror = () => reject(getReq.error);
  });
}

// ── Sync all pending to the API ───────────────────────────────────────────────

export async function syncPending(apiInstance: ApiLike): Promise<SyncResult> {
  if (!navigator.onLine) return { synced: 0, failed: 0, abandoned: 0 };

  const db = await openDB();
  const pending = await getAllPending();
  let synced = 0, failed = 0, abandoned = 0;

  for (const entry of pending) {
    if (entry.abandonada) continue;
    const { id, queued_at: _queued_at, synced: _s, retries: _r, _dueno_user: _du, _dueno_org: _do, abandonada: _ab, ...payload } = entry; // strip queue-only fields
    const currentRetries = entry.retries ?? 0;

    try {
      await apiInstance.post('/imputations', payload as Record<string, unknown>);
      await deleteEntry(Number(id));
      synced++;
    } catch {
      const reintentos = currentRetries + 1;
      await updateRetries(db, Number(id), reintentos, reintentos >= MAX_RETRY_ATTEMPTS);
      if (reintentos >= MAX_RETRY_ATTEMPTS) abandoned++; else failed++;
    }
  }

  if (abandoned > 0) {
    try { window.dispatchEvent(new CustomEvent('offline:imputaciones-abandonadas', { detail: { count: abandoned } })); } catch { /* accesorio: sin window (tests) */ }
  }
  return { synced, failed, abandoned };
}

// ── Auto-sync on reconnect ────────────────────────────────────────────────────

let _apiRef: ApiLike | null = null;
let _onSyncCallback: ((result: SyncResult) => void) | null = null;

export function initOfflineSync(apiInstance: ApiLike, onSync?: (result: SyncResult) => void) {
  _apiRef = apiInstance;
  _onSyncCallback = onSync ?? null;

  window.addEventListener('online', async () => {
    const result = await syncPending(apiInstance);
    if (_onSyncCallback) _onSyncCallback(result);
  });
}
