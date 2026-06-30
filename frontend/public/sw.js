// ─── Lumen Service Worker — Session 19: Offline-first PWA ────────────────────
// Cache strategies:
//   App shell (HTML/JS/CSS): cache-first
//   API calls:               network-first, no cache
//   Map tiles (OSM):         cache-first with 204 fallback
// Background Sync:           tag 'lumen-offline-sync'

const CACHE_NAME = 'lumen-v1';
const TILE_CACHE_NAME = 'lumen-v1-tiles';
const OFFLINE_QUEUE_DB = 'lumen-offline';
const OFFLINE_QUEUE_STORE = 'drafts';

// Static assets to cache on install (app shell)
const APP_SHELL = [
  '/',
  '/index.html',
  '/manifest.json',
];

// ── Install: cache app shell ──────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(APP_SHELL);
    }).then(() => self.skipWaiting())
  );
});

// ── Activate: clean old caches ────────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME && key !== TILE_CACHE_NAME)
          .map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// ── Fetch: strategy based on request type ─────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET and Chrome extension requests
  if (event.request.method !== 'GET') return;
  if (url.protocol === 'chrome-extension:') return;

  // API calls: network-first, no cache
  if (url.pathname.startsWith('/api/') || url.port === '8000') {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(
          JSON.stringify({ error: 'offline', message: 'No internet connection' }),
          { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
      })
    );
    return;
  }

  // Map tiles: cache-first with network fallback
  if (url.hostname.includes('tile.openstreetmap.org')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (response.ok) {
            const responseClone = response.clone();
            caches.open(TILE_CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone);
            });
          }
          return response;
        }).catch(() => {
          // Return a blank response tile if offline
          return new Response('', { status: 204 });
        });
      })
    );
    return;
  }

  // App shell and static assets: cache-first
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        if (response.ok && response.type !== 'opaque') {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      }).catch(() => {
        // Return cached index.html for navigation requests (SPA fallback)
        if (event.request.mode === 'navigate') {
          return caches.match('/index.html');
        }
        return new Response('', { status: 204 });
      });
    })
  );
});

// ── Background sync ───────────────────────────────────────────────────────────
self.addEventListener('sync', (event) => {
  if (event.tag === 'lumen-offline-sync') {
    event.waitUntil(syncOfflineDrafts());
  }
});

async function syncOfflineDrafts() {
  const db = await openDB();
  const drafts = await getAllDrafts(db);

  if (drafts.length === 0) return;

  try {
    const response = await fetch('/api/offline/sync', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        drafts: drafts.map((d) => ({
          device_idempotency_key: d.key,
          created_locally_at:    d.created_at,
          title:       d.payload.title || d.payload.description.slice(0, 60),
          description: d.payload.description,
          category_id: d.payload.category_id || null,
          latitude:    d.payload.latitude || 0,
          longitude:   d.payload.longitude || 0,
          address:     d.payload.address || undefined,
          is_anonymous:  d.payload.is_anonymous || false,
          is_emergency:  d.payload.is_emergency || false,
          severity:    'medium',
        })),
      }),
    });

    if (response.ok) {
      const result = await response.json();
      // Remove synced and skipped drafts from IndexedDB
      const synced = [...(result.synced || []), ...(result.skipped || [])];
      for (const item of synced) {
        await deleteDraft(db, item.key);
      }
      // Notify all open clients
      const clients = await self.clients.matchAll();
      clients.forEach((client) => {
        client.postMessage({
          type: 'OFFLINE_SYNC_COMPLETE',
          synced: result.synced,
          skipped: result.skipped,
          failed: result.failed,
        });
      });
    }
  } catch (err) {
    // Sync failed — will retry on next sync event
    console.warn('[Lumen SW] Background sync failed:', err);
  }
}

// ── IndexedDB helpers ─────────────────────────────────────────────────────────
function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(OFFLINE_QUEUE_DB, 1);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(OFFLINE_QUEUE_STORE)) {
        db.createObjectStore(OFFLINE_QUEUE_STORE, { keyPath: 'key' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function getAllDrafts(db) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readonly');
    const store = tx.objectStore(OFFLINE_QUEUE_STORE);
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function deleteDraft(db, key) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readwrite');
    const store = tx.objectStore(OFFLINE_QUEUE_STORE);
    const req = store.delete(key);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}
