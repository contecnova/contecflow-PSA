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

// ── Open DB ──────────────────────────────────────────────────────────────────

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
        store.createIndex('queued_at', 'queued_at', { unique: false });
      }
    };
    req.onsuccess  = (e) => resolve(e.target.result);
    req.onerror    = (e) => reject(e.target.error);
  });
}

// ── Queue an imputation for later sync ───────────────────────────────────────

export async function queueImputation(payload) {
  const db    = await openDB();
  const entry = { ...payload, queued_at: new Date().toISOString(), synced: false, retries: 0 };
  return new Promise((resolve, reject) => {
    const tx   = db.transaction(STORE, 'readwrite');
    const req  = tx.objectStore(STORE).add(entry);
    req.onsuccess = () => resolve(req.result);   // returns generated id
    req.onerror   = (e) => reject(e.target.error);
  });
}

// ── Count pending entries ─────────────────────────────────────────────────────

export async function pendingCount() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).count();
    req.onsuccess = () => resolve(req.result);
    req.onerror   = (e) => reject(e.target.error);
  });
}

// ── Get all pending entries ───────────────────────────────────────────────────

export async function getAllPending() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror   = (e) => reject(e.target.error);
  });
}

// ── Delete a synced entry ─────────────────────────────────────────────────────

async function deleteEntry(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE, 'readwrite');
    const req = tx.objectStore(STORE).delete(id);
    req.onsuccess = () => resolve();
    req.onerror   = (e) => reject(e.target.error);
  });
}

// ── Update retry count for an entry ──────────────────────────────────────────

async function updateRetries(db, id, retries) {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(STORE, 'readwrite');
    const store = tx.objectStore(STORE);
    const getReq = store.get(id);
    getReq.onsuccess = () => {
      const entry = getReq.result;
      if (!entry) { resolve(); return; }
      const putReq = store.put({ ...entry, retries });
      putReq.onsuccess = () => resolve();
      putReq.onerror   = (e) => reject(e.target.error);
    };
    getReq.onerror = (e) => reject(e.target.error);
  });
}

// ── Sync all pending to the API ───────────────────────────────────────────────

export async function syncPending(apiInstance) {
  if (!navigator.onLine) return { synced: 0, failed: 0, abandoned: 0 };

  const db = await openDB();
  const pending = await getAllPending();
  let synced = 0, failed = 0, abandoned = 0;

  for (const entry of pending) {
    const { id, queued_at: _queued_at, synced: _s, retries: _r, ...payload } = entry; // strip queue-only fields
    const currentRetries = entry.retries ?? 0;

    if (currentRetries >= MAX_RETRY_ATTEMPTS) {
      // Exceeded max retries — remove to avoid blocking the queue indefinitely
      await deleteEntry(id);
      abandoned++;
      continue;
    }

    try {
      await apiInstance.post('/imputations', payload);
      await deleteEntry(id);
      synced++;
    } catch {
      await updateRetries(db, id, currentRetries + 1);
      failed++;
    }
  }

  return { synced, failed, abandoned };
}

// ── Auto-sync on reconnect ────────────────────────────────────────────────────

let _apiRef = null;
let _onSyncCallback = null;

export function initOfflineSync(apiInstance, onSync) {
  _apiRef = apiInstance;
  _onSyncCallback = onSync;

  window.addEventListener('online', async () => {
    const result = await syncPending(apiInstance);
    if (_onSyncCallback) _onSyncCallback(result);
  });
}
