import type { PriisData } from '../types/priis';
import { API_BASE } from '../config';
import { AgencySchema, VendorSchema, SiteSchema, ContractSchema, EventRecordSchema, AnomalySchema, SourceRecordSchema, InvestigationSchema, AlertRecordSchema } from '../schemas/priis';

export interface LocalDataset {
  schema: 'spiderweb-local-dataset/v1';
  id: string;
  sourceScope: string;
  savedAt: string;
  sourceKind: 'live' | 'demo';
  data: PriisData;
}
const scope = new URL(API_BASE || '/', window.location.origin).href;
const validators = { agencies: AgencySchema, vendors: VendorSchema, sites: SiteSchema, contracts: ContractSchema, events: EventRecordSchema, anomalies: AnomalySchema, sources: SourceRecordSchema, investigations: InvestigationSchema, alerts: AlertRecordSchema };

/** Validate without synthesizing rows, normalizing strings, or discarding failures. */
export function validDataset(value: unknown): value is PriisData {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  for (const [key, validator] of Object.entries(validators)) {
    const rows = data[key];
    if (!Array.isArray(rows) || rows.length > 100000) return false;
    const ids = new Set<string>();
    for (const row of rows as unknown[]) {
      if (!row || typeof row !== 'object') return false;
      const id = (row as Record<string, unknown>).id;
      if (!validator.safeParse(row).success || typeof id !== 'string' || !id || ids.has(id)) return false;
      ids.add(id);
    }
  }
  return Array.isArray(data.watchlist) && (data.watchlist as unknown[]).every(row => {
    if (!row || typeof row !== 'object') return false;
    const item = row as Record<string, unknown>;
    return typeof item.id === 'string' && typeof item.kind === 'string' && ['agency','vendor','contract','site','event','anomaly','source','investigation','finding'].includes(item.kind);
  });
}

function validSnapshot(value: unknown): value is LocalDataset {
  if (!value || typeof value !== 'object') return false;
  const row = value as Record<string, unknown>;
  return row.schema === 'spiderweb-local-dataset/v1' && row.sourceScope === scope
    && typeof row.id === 'string' && typeof row.savedAt === 'string' && Number.isFinite(Date.parse(row.savedAt))
    && (row.sourceKind === 'live' || row.sourceKind === 'demo') && validDataset(row.data);
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('spiderweb-local-datasets-v1', 1);
    let expired = false;
    const timer = setTimeout(() => { expired = true; reject(new Error('Local storage is blocked')); }, 3000);
    request.onupgradeneeded = () => {
      const db = request.result;
      db.createObjectStore('snapshots', { keyPath: 'id' });
      db.createObjectStore('heads');
    };
    request.onerror = () => { clearTimeout(timer); reject(request.error ?? new Error('Local storage unavailable')); };
    request.onsuccess = () => {
      clearTimeout(timer);
      if (expired) { request.result.close(); return; }
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
  });
}

export async function saveLocalDataset(data: PriisData, sourceKind: 'live' | 'demo'): Promise<LocalDataset> {
  if (!validDataset(data)) throw new Error('Dataset validation failed; existing local copies were preserved');
  const snapshot: LocalDataset = { schema: 'spiderweb-local-dataset/v1', id: crypto.randomUUID(), sourceScope: scope, savedAt: new Date().toISOString(), sourceKind, data };
  const db = await open();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(['snapshots', 'heads'], 'readwrite');
      transaction.objectStore('snapshots').add(snapshot);
      transaction.objectStore('heads').put(snapshot.id, scope);
      transaction.oncomplete = () => resolve();
      transaction.onabort = () => reject(transaction.error ?? new Error('Local save aborted'));
      transaction.onerror = () => reject(transaction.error ?? new Error('Local save failed'));
    });
    return snapshot;
  } finally { db.close(); }
}

export async function loadLocalDataset(): Promise<LocalDataset | null> {
  let db: IDBDatabase | undefined;
  try {
    db = await open();
    return await new Promise<LocalDataset | null>((resolve, reject) => {
      const transaction = db!.transaction(['snapshots', 'heads'], 'readonly');
      let snapshot: unknown = null;
      const head = transaction.objectStore('heads').get(scope);
      head.onsuccess = () => {
        const id: unknown = head.result;
        if (typeof id !== 'string' || !id) return;
        const request = transaction.objectStore('snapshots').get(id);
        request.onsuccess = () => { snapshot = request.result as unknown; };
      };
      transaction.oncomplete = () => resolve(validSnapshot(snapshot) ? snapshot : null);
      transaction.onabort = () => reject(transaction.error ?? new Error('Local read aborted'));
    });
  } catch { return null; } finally { db?.close(); }
}
