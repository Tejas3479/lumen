/**
 * useOfflineQueue
 * Manages the offline draft queue in IndexedDB.
 * Exposes saveDraft, syncDrafts, loadDrafts, and removeDraft.
 *
 * Used by:
 *  - ReportIssueModal — saves draft when offline submission fails
 *  - HomePage         — loads drafts on mount to hydrate appStore
 *  - OfflineSyncBanner — reads pendingDrafts from appStore (count)
 */
import { useCallback } from 'react';
import { useAppStore } from '@/store/appStore';
import type { PendingDraft } from '@/store/appStore';
import type { ReportFormDraft } from '@/types';

const DB_NAME = 'lumen-offline';
const STORE_NAME = 'drafts';
const DB_VERSION = 1;

// ── IndexedDB helpers ─────────────────────────────────────────────────────────

async function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        // keyPath 'key' matches SW IndexedDB schema for idempotency
        db.createObjectStore(STORE_NAME, { keyPath: 'key' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

interface IDBDraftRecord {
  key: string;           // = idempotency_key
  payload: Omit<ReportFormDraft, 'media_files'>;
  created_at: string;
  sync_status: 'pending' | 'syncing' | 'failed';
}

async function idbPut(record: IDBDraftRecord): Promise<void> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const req = store.put(record);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
    tx.oncomplete = () => db.close();
  });
}

async function idbGetAll(): Promise<IDBDraftRecord[]> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const req = store.getAll();
    req.onsuccess = () => {
      resolve(req.result);
      db.close();
    };
    req.onerror = () => reject(req.error);
  });
}

async function idbDelete(key: string): Promise<void> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const req = store.delete(key);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
    tx.oncomplete = () => db.close();
  });
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useOfflineQueue() {
  const addPendingDraft = useAppStore((s) => s.addPendingDraft);
  const removePendingDraft = useAppStore((s) => s.removePendingDraft);
  const updateDraftStatus = useAppStore((s) => s.updateDraftStatus);
  const offlineQueueCount = useAppStore((s) => s.offlineQueueCount);

  /**
   * Persist a report draft to IndexedDB and add to appStore.
   * Called when form submission fails due to network error.
   */
  const saveDraft = useCallback(async (draft: ReportFormDraft): Promise<void> => {
    const record: IDBDraftRecord = {
      key: draft.idempotency_key,
      payload: {
        step: draft.step,
        category_id: draft.category_id,
        category_name: draft.category_name,
        title: draft.title,
        description: draft.description,
        is_emergency: draft.is_emergency,
        is_anonymous: draft.is_anonymous,
        latitude: draft.latitude,
        longitude: draft.longitude,
        address: draft.address,
        idempotency_key: draft.idempotency_key,
      },
      created_at: new Date().toISOString(),
      sync_status: 'pending',
    };

    const pendingDraft: PendingDraft = {
      idempotency_key: draft.idempotency_key,
      created_at: record.created_at,
      sync_status: 'pending',
      draft: {
        title: draft.title,
        description: draft.description,
        category_id: draft.category_id,
        latitude: draft.latitude,
        longitude: draft.longitude,
        address: draft.address,
        is_anonymous: draft.is_anonymous,
        is_emergency: draft.is_emergency,
      },
    };

    try {
      await idbPut(record);
      addPendingDraft(pendingDraft);
    } catch (err) {
      console.error('[useOfflineQueue] Failed to save offline draft:', err);
    }
  }, [addPendingDraft]);

  /**
   * Load all drafts from IndexedDB and hydrate appStore.
   * Called on HomePage mount.
   */
  const loadDrafts = useCallback(async (): Promise<void> => {
    try {
      const records = await idbGetAll();
      records
        .filter((r) => r.sync_status === 'pending')
        .forEach((r) => {
          const pending: PendingDraft = {
            idempotency_key: r.key,
            created_at: r.created_at,
            sync_status: r.sync_status as 'pending',
            draft: {
              title: r.payload.title,
              description: r.payload.description,
              category_id: r.payload.category_id,
              latitude: r.payload.latitude,
              longitude: r.payload.longitude,
              address: r.payload.address,
              is_anonymous: r.payload.is_anonymous,
              is_emergency: r.payload.is_emergency,
            },
          };
          // Only add if not already in store
          const existing = useAppStore.getState().pendingDrafts;
          if (!existing.find((d) => d.idempotency_key === r.key)) {
            addPendingDraft(pending);
          }
        });
    } catch (err) {
      console.warn('[useOfflineQueue] Failed to load offline drafts:', err);
    }
  }, [addPendingDraft]);

  /**
   * Remove a specific draft from IndexedDB and appStore.
   */
  const removeDraft = useCallback(async (key: string): Promise<void> => {
    try {
      await idbDelete(key);
      removePendingDraft(key);
    } catch (err) {
      console.error('[useOfflineQueue] Failed to remove draft:', err);
    }
  }, [removePendingDraft]);

  const markDraftSyncing = useCallback((key: string) => {
    updateDraftStatus(key, 'syncing');
  }, [updateDraftStatus]);

  const markDraftSynced = useCallback(async (key: string) => {
    updateDraftStatus(key, 'syncing'); // intermediate state
    await removeDraft(key);
  }, [updateDraftStatus, removeDraft]);

  const markDraftFailed = useCallback((key: string) => {
    updateDraftStatus(key, 'failed');
  }, [updateDraftStatus]);

  /**
   * Register Background Sync if supported.
   * Falls back gracefully — OfflineSyncBanner handles manual retry.
   */
  const requestBackgroundSync = useCallback(async (): Promise<void> => {
    if ('serviceWorker' in navigator && 'SyncManager' in window) {
      try {
        const registration = await navigator.serviceWorker.ready;
        await (registration as ServiceWorkerRegistration & { sync: { register: (tag: string) => Promise<void> } })
          .sync.register('lumen-offline-sync');
      } catch {
        // Background sync not supported — silent fallback
      }
    }
  }, []);

  return {
    // Legacy shape (keeps existing OfflineSyncBanner compatibility)
    queue: useAppStore.getState().pendingDrafts,
    queueCount: offlineQueueCount,
    addToQueue: saveDraft,
    syncQueue: async () => { /* handled by SW background sync */ },
    clearQueue: () => { /* handled per-draft */ },

    // Full API
    saveDraft,
    loadDrafts,
    removeDraft,
    markDraftSyncing,
    markDraftSynced,
    markDraftFailed,
    requestBackgroundSync,
  };
}
