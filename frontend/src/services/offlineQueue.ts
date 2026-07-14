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

interface QueueEntry extends Record<string, unknown> {
  id?: number
  queued_at: string
  synced: boolean
  retries: number
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
  const db    = await openDB();
  const entry: QueueEntry = { ...payload, queued_at: new Date().toISOString(), synced: false, retries: 0 };
  return new Promise((resolve, reject) => {
    const tx   = db.transaction(STORE, 'readwrite');
    const req  = tx.objectStore(STORE).add(entry);
    req.onsuccess = () => resolve(Number(req.result));   // returns generated id
    req.onerror   = () => reject(req.error);
  });
}

// ── Count pending entries ─────────────────────────────────────────────────────

export async function pendingCount(): Promise<number> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).count();
    req.onsuccess = () => resolve(req.result);
    req.onerror   = () => reject(req.error);
  });
}

// ── Get all pending entries ───────────────────────────────────────────────────

export async function getAllPending(): Promise<QueueEntry[]> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve((req.result as QueueEntry[]) || []);
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

async function updateRetries(db: IDBDatabase, id: number, retries: number) {
  return new Promise<void>((resolve, reject) => {
    const tx  = db.transaction(STORE, 'readwrite');
    const store = tx.objectStore(STORE);
    const getReq = store.get(id);
    getReq.onsuccess = () => {
      const entry = getReq.result as QueueEntry | undefined;
      if (!entry) { resolve(undefined); return; }
      const putReq = store.put({ ...entry, retries });
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
    const { id, queued_at: _queued_at, synced: _s, retries: _r, ...payload } = entry; // strip queue-only fields
    const currentRetries = entry.retries ?? 0;

    if (currentRetries >= MAX_RETRY_ATTEMPTS) {
      // Exceeded max retries — remove to avoid blocking the queue indefinitely
      await deleteEntry(Number(id));
      abandoned++;
      continue;
    }

    try {
      await apiInstance.post('/imputations', payload as Record<string, unknown>);
      await deleteEntry(Number(id));
      synced++;
    } catch {
      await updateRetries(db, Number(id), currentRetries + 1);
      failed++;
    }
  }

  return { synced, failed, abandoned };
}

// ── Auto-sync on reconnect ────────────────────────────────────────────────────

let _apiRef: ApiLike | null = null;
let _onSyncCallback: ((result: SyncResult) => void) | null = null;

export function initOfflineSync(apiInstance: ApiLike, onSync?: (result: SyncResult) => void) {
  _apiRef = apiInstance;
  _onSyncCallback = onSync;

  window.addEventListener('online', async () => {
    const result = await syncPending(apiInstance);
    if (_onSyncCallback) _onSyncCallback(result);
  });
}
