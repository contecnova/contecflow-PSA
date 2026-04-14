/**
 * offlineQueue.js — IndexedDB queue for offline time imputations
 *
 * When the user registers time while offline, the entry is stored here.
 * On reconnect (online event or manual sync), pending entries are POSTed
 * to /api/v1/imputations in order and removed from the queue.
 */

const DB_NAME   = 'clarive_offline';
const DB_VERSION = 1;
const STORE     = 'imputations_queue';

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
  const entry = { ...payload, queued_at: new Date().toISOString(), synced: false };
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

// ── Sync all pending to the API ───────────────────────────────────────────────

export async function syncPending(apiInstance) {
  if (!navigator.onLine) return { synced: 0, failed: 0 };

  const pending = await getAllPending();
  let synced = 0, failed = 0;

  for (const entry of pending) {
    const { id, _queued_at, synced: _s, ...payload } = entry; // strip queue-only fields
    try {
      await apiInstance.post('/imputations', payload);
      await deleteEntry(id);
      synced++;
    } catch {
      failed++;
    }
  }

  return { synced, failed };
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
