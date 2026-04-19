// IndexedDB video chunk store — survives browser crash (CLAUDE.md §9.6).
const DB_NAME = "imu-video-backup";
const DB_VERSION = 1;
const STORE = "chunks";

async function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE, { keyPath: "key" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveChunk(sessionId: string, index: number, blob: Blob): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put({ key: `${sessionId}_${index}`, sessionId, index, blob });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function loadChunks(sessionId: string): Promise<Blob[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => {
      const all = (req.result as Array<{ key: string; sessionId: string; index: number; blob: Blob }>)
        .filter(r => r.sessionId === sessionId)
        .sort((a, b) => a.index - b.index);
      resolve(all.map(r => r.blob));
    };
    req.onerror = () => reject(req.error);
  });
}

export async function clearChunks(sessionId: string): Promise<void> {
  const db = await openDb();
  const chunks = await loadChunks(sessionId);
  if (chunks.length === 0) return;
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    // Delete by key prefix
    const req = store.openCursor();
    req.onsuccess = () => {
      const cursor = req.result;
      if (!cursor) return;
      if ((cursor.value as { sessionId: string }).sessionId === sessionId) {
        cursor.delete();
      }
      cursor.continue();
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function hasPendingChunks(sessionId: string): Promise<boolean> {
  const chunks = await loadChunks(sessionId);
  return chunks.length > 0;
}
