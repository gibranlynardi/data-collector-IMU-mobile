// IndexedDB video chunk store — survives browser crash (CLAUDE.md §9.6).
// Multi-camera: chunks are namespaced per (sessionId, camId) so N cameras never collide.
const DB_NAME = "imu-video-backup";
const DB_VERSION = 1;
const STORE = "chunks";

interface ChunkRecord {
  key: string;
  sessionId: string;
  camId: string;
  index: number;
  blob: Blob;
}

async function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      // keyPath unchanged from v1; create the store only if it does not exist yet.
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE, { keyPath: "key" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function chunkKey(sessionId: string, camId: string, index: number): string {
  // "__" separators: sessionId is epoch-ms digits, camId is "camN", index is an int —
  // none contain "__", so keys are unambiguous.
  return `${sessionId}__${camId}__${index}`;
}

export async function saveChunk(
  sessionId: string, camId: string, index: number, blob: Blob,
): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const rec: ChunkRecord = { key: chunkKey(sessionId, camId, index), sessionId, camId, index, blob };
    tx.objectStore(STORE).put(rec);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function loadChunks(sessionId: string, camId: string): Promise<Blob[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => {
      const all = (req.result as ChunkRecord[])
        .filter(r => r.sessionId === sessionId && r.camId === camId)
        .sort((a, b) => a.index - b.index);
      resolve(all.map(r => r.blob));
    };
    req.onerror = () => reject(req.error);
  });
}

// camId omitted → clear every camera's chunks for that session.
export async function clearChunks(sessionId: string, camId?: string): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const req = tx.objectStore(STORE).openCursor();
    req.onsuccess = () => {
      const cursor = req.result;
      if (!cursor) return;
      const v = cursor.value as ChunkRecord;
      if (v.sessionId === sessionId && (camId === undefined || v.camId === camId)) {
        cursor.delete();
      }
      cursor.continue();
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// Wipe the ENTIRE chunk store regardless of session/cam. Called at the start of a new session
// so the PREVIOUS session's chunks persist (recoverable) until then — see audit Finding A.
export async function clearAllChunks(): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// Distinct camIds that still have chunks on disk for a session (crash-recovery aid; §6).
export async function listPendingCameras(sessionId: string): Promise<string[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => {
      const cams = new Set<string>();
      (req.result as ChunkRecord[]).forEach(r => { if (r.sessionId === sessionId) cams.add(r.camId); });
      resolve(Array.from(cams));
    };
    req.onerror = () => reject(req.error);
  });
}

export async function hasPendingChunks(sessionId: string): Promise<boolean> {
  return (await listPendingCameras(sessionId)).length > 0;
}
