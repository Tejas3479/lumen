# Lumen — Offline System

## Overview

Lumen is a Progressive Web App (PWA) designed to function even when the user has no network connectivity. Citizens in areas with intermittent connectivity (rural edges, underground car parks, cellular dead zones) can still capture and queue issue reports; the system automatically submits them when connectivity is restored.

---

## Service Worker Strategy

The Lumen service worker (`/public/sw.js`) applies three distinct caching strategies by request type:

### 1. Cache-First: App Shell

Static assets (HTML, JS bundles, CSS, fonts, icons) are served from the cache first. On first visit, the service worker caches the entire app shell. On subsequent visits, the shell loads instantly from cache even if the network is unavailable.

```
Request: /index.html, /assets/*.js, /assets/*.css
Strategy: Cache-First
Fallback: Offline shell page (bare Lumen UI with "You are offline" state)
```

### 2. Network-First: API Calls

All requests to `/issues`, `/auth`, `/analytics`, etc. go network-first. If the network request succeeds, the response is cached for 5 minutes. If the network is unavailable:
- `GET` requests return the last cached response.
- `POST`/`PATCH`/`DELETE` requests are intercepted and queued (see Draft Queue below).

```
Request: /api/* or /issues/*
Strategy: Network-First with 5-second timeout
Cache Duration: 5 minutes for GET responses
On Failure: Queue POST/PATCH, return cached GET
```

### 3. Tile Cache: Map Tiles

Leaflet map tiles are cached indefinitely (up to 500 tiles, ~25MB). Tiles are cached as they are viewed. If a tile is not in cache and the network is unavailable, a grey placeholder tile is shown.

```
Request: *.tile.openstreetmap.org/*
Strategy: Cache-First with 500-tile LRU eviction
Cache Duration: 7 days
```

---

## IndexedDB Schema: Draft Queue

Offline drafts are stored in IndexedDB under the database name `lumen-offline-v1`, object store `drafts`.

```typescript
interface OfflineDraft {
  // Idempotency key — generated on form open, never changes
  device_idempotency_key: string;   // UUID v4, e.g. "3f7a..."

  // Submission data (mirrors POST /issues form fields)
  title: string;
  description: string;
  latitude: number;
  longitude: number;
  address?: string;
  ward?: string;
  severity: "low" | "medium" | "high" | "critical";
  is_anonymous: boolean;
  is_emergency: boolean;
  category_id?: string;

  // Offline metadata
  created_locally_at: string;  // ISO timestamp of when draft was captured
  synced: boolean;             // false = pending, true = submitted
  synced_issue_id?: string;    // populated after successful sync
  media_blobs?: Blob[];        // captured photos before upload
}
```

**IndexedDB indexes:**
- `device_idempotency_key` (unique) — for rapid lookup and deduplication
- `synced` — for querying all pending drafts
- `created_locally_at` — for ordering draft queue display

---

## Idempotency Key Lifecycle

The idempotency key is the cornerstone of safe offline sync. It prevents the same draft from being submitted as two separate issues if the sync is interrupted or retried.

```
1. User opens ReportIssueModal
   → Frontend generates UUID v4: device_idempotency_key = "3f7a-..."
   → Key stored in component state AND in the IndexedDB draft immediately

2. User fills out form → media captured offline
   → Draft updated in IndexedDB

3. User taps Submit (online):
   → POST /issues with offline_draft_id = "3f7a-..."
   → Server checks: SELECT FROM offline_drafts WHERE device_idempotency_key = "3f7a-..." AND synced = true
   → If found: return existing issue_id (skip creation)
   → If not found: create issue, upsert offline_draft record as synced=true
   → Draft marked synced in IndexedDB

4. User taps Submit (offline):
   → Draft saved to IndexedDB with synced=false
   → Background Sync registered

5. Background Sync fires (connectivity restored):
   → POST /offline/sync with batch of pending drafts
   → For each draft: same idempotency check as step 3
   → Result returned: {synced: [...], skipped: [...], failed: [...]}
   → IndexedDB updated: synced=true for successful drafts

6. If sync attempt interrupted mid-batch:
   → Retry only drafts still marked synced=false in IndexedDB
   → Server ignores already-synced keys (skipped list)
```

---

## Background Sync API Integration

The Background Sync API allows the browser to defer sync operations to when connectivity is stable, even if the user has navigated away from the app.

```typescript
// Register sync when a draft is saved offline
async function registerOfflineSync() {
  const sw = await navigator.serviceWorker.ready;
  await sw.sync.register('lumen-draft-sync');
}

// Service worker sync event handler
self.addEventListener('sync', async (event: SyncEvent) => {
  if (event.tag === 'lumen-draft-sync') {
    event.waitUntil(syncPendingDrafts());
  }
});

async function syncPendingDrafts() {
  const db = await openDB('lumen-offline-v1');
  const pending = await db.getAllFromIndex('drafts', 'synced', false);
  
  if (pending.length === 0) return;
  
  const response = await fetch('/offline/sync', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': getStoredToken() },
    body: JSON.stringify({ drafts: pending }),
  });
  
  const result = await response.json();
  // Mark synced drafts as synced=true in IndexedDB
  for (const item of result.synced) {
    await db.put('drafts', { ...pending.find(d => d.device_idempotency_key === item.key), synced: true, synced_issue_id: item.issue_id });
  }
}
```

**Fallback (Safari and non-Chromium browsers):**
Since Background Sync is not supported in WebKit, the app also registers a `window.addEventListener('online', ...)` handler that triggers sync immediately when `navigator.onLine` transitions to `true`.

---

## appStore.pendingDrafts State Management

The Zustand `appStore` tracks the offline draft queue in memory:

```typescript
interface AppState {
  pendingDrafts: OfflineDraft[];         // All unsynced drafts
  pendingDraftCount: number;             // Convenience count for badge
  addDraft: (draft: OfflineDraft) => void;
  removeDraft: (key: string) => void;
  markDraftSynced: (key: string, issueId: string) => void;
  loadDraftsFromIndexedDB: () => Promise<void>;
}
```

**Lifecycle:**
- On app startup: `loadDraftsFromIndexedDB()` hydrates store from IndexedDB.
- On draft creation: `addDraft()` writes to IndexedDB then updates store.
- On successful sync: `markDraftSynced()` updates both IndexedDB and store.
- `pendingDraftCount` drives the OfflineSyncBanner count badge.

---

## OfflineSyncBanner UX

When `pendingDraftCount > 0`, the `OfflineSyncBanner` component renders at the top of the screen:

```
┌─────────────────────────────────────────────────────────┐
│  📶  2 reports pending sync   [Sync Now]  [×]           │
└─────────────────────────────────────────────────────────┘
```

- **"Sync Now"** button triggers `syncPendingDrafts()` immediately.
- **[×]** dismisses the banner for the session (drafts remain in queue).
- Banner uses `aria-live="polite"` for screen reader announcement.
- Banner disappears automatically when all drafts sync successfully.

When offline and drafts exist:
```
┌─────────────────────────────────────────────────────────┐
│  📵  You are offline. 2 reports saved locally.          │
└─────────────────────────────────────────────────────────┘
```

---

## POST /offline/sync Deduplication Logic

The server-side sync endpoint processes drafts in a batch with full idempotency:

```
POST /offline/sync
{
  "drafts": [
    { "device_idempotency_key": "3f7a-...", "title": "...", ... },
    { "device_idempotency_key": "8b2c-...", "title": "...", ... }
  ]
}
```

**Per-draft processing:**

```python
for draft in payload.drafts:
    key = draft.device_idempotency_key

    # 1. Check if already processed
    existing_draft = await db.get(OfflineDraft, key=key)
    
    if existing_draft and existing_draft.synced:
        result.skipped.append(SkippedResult(key=key, issue_id=str(existing_draft.synced_issue_id)))
        continue  # ← idempotency: return cached result, no duplicate

    # 2. Create issue (reuses same create_issue service as POST /issues)
    issue = await create_issue(payload=IssueCreate(...), db=db, reporter=current_user)

    # 3. Upsert offline_draft record
    if existing_draft:
        existing_draft.synced = True
        existing_draft.synced_issue_id = issue.id
    else:
        db.add(OfflineDraft(device_idempotency_key=key, synced=True, synced_issue_id=issue.id, ...))

    result.synced.append(SyncedResult(key=key, issue_id=str(issue.id)))
```

**Response structure:**
```json
{
  "synced": [{"key": "3f7a-...", "issue_id": "uuid"}],
  "skipped": [{"key": "8b2c-...", "issue_id": "existing-uuid"}],
  "failed": [{"key": "9d1e-...", "error": "Validation error: title too short"}]
}
```

Key properties:
- `failed` items do **not** abort the batch — the endpoint always returns 200.
- Each failed item should be retried by the client on next sync attempt.
- `skipped` items have `issue_id` populated so the client can link the draft to the existing issue.
- Batch size capped at **50 drafts per request** (`max_length=50` on `OfflineSyncRequest.drafts`).

---

## Offline Limitations

See [LIMITATIONS.md §3](LIMITATIONS.md) for:
- Background Sync API browser support (Safari limitation)
- Offline map tile coverage
- IndexedDB quota limits
