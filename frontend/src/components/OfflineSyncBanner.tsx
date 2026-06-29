/**
 * OfflineSyncBanner
 *
 * Sticky banner that:
 *  - Displays when the user is offline (amber, WifiOff icon)
 *  - Displays while pending drafts are uploading after coming back online (green)
 *  - Auto-triggers offline sync when connectivity is restored
 *  - Provides a manual retry button
 *
 * Reads: appStore.isOnline, appStore.pendingDrafts
 * Writes: appStore.removePendingDraft, appStore.updateDraftStatus
 *
 * Note: pendingDrafts is populated by Session 19 (PWA / IndexedDB).
 * Until then the banner only shows the offline/online network state.
 */
import { useEffect, useCallback } from 'react';
import { Wifi, WifiOff, RefreshCw } from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import api from '@/lib/api';

export default function OfflineSyncBanner() {
  const isOnline          = useAppStore((s) => s.isOnline);
  const pendingDrafts     = useAppStore((s) => s.pendingDrafts);
  const updateDraftStatus = useAppStore((s) => s.updateDraftStatus);
  const removePendingDraft = useAppStore((s) => s.removePendingDraft);

  const pendingCount = pendingDrafts.filter(
    (d) => d.sync_status === 'pending'
  ).length;

  // ── Sync function ───────────────────────────────────────────────
  const syncDrafts = useCallback(async () => {
    const pending = pendingDrafts.filter((d) => d.sync_status === 'pending');
    if (pending.length === 0) return;

    // Optimistically mark all as syncing
    pending.forEach((d) => updateDraftStatus(d.idempotency_key, 'syncing'));

    try {
      const payload = pending.map((d) => ({
        device_idempotency_key: d.idempotency_key,
        created_locally_at:    d.created_at,
        title:       d.draft.title ?? d.draft.description.slice(0, 60),
        description: d.draft.description,
        category_id: d.draft.category_id ?? null,
        latitude:    d.draft.latitude    ?? 0,
        longitude:   d.draft.longitude   ?? 0,
        address:     d.draft.address     ?? undefined,
        is_anonymous:  d.draft.is_anonymous  ?? false,
        is_emergency:  d.draft.is_emergency  ?? false,
      }));

      const response = await api.post<{
        synced:  Array<{ key: string; issue_id: string }>;
        skipped: Array<{ key: string; issue_id: string }>;
        failed:  Array<{ key: string; error: string }>;
      }>('/offline/sync', { drafts: payload });

      const { data } = response;

      // Remove successfully uploaded drafts
      data.synced.forEach((item) => removePendingDraft(item.key));
      data.skipped.forEach((item) => removePendingDraft(item.key));

      // Mark failures so the user can retry
      data.failed.forEach((item) =>
        updateDraftStatus(item.key, 'failed')
      );
    } catch {
      // Roll back to 'pending' so the retry button stays visible
      pending.forEach((d) => updateDraftStatus(d.idempotency_key, 'failed'));
    }
  }, [pendingDrafts, updateDraftStatus, removePendingDraft]);

  // ── Auto-sync on reconnect ──────────────────────────────────────
  useEffect(() => {
    if (isOnline && pendingCount > 0) {
      syncDrafts();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOnline]);

  // Hide when online and nothing is queued
  if (isOnline && pendingCount === 0) return null;

  // ── Render ──────────────────────────────────────────────────────
  return (
    <div
      className={[
        'sticky top-0 z-50 w-full',
        'flex items-center gap-3 px-4 py-2.5',
        'text-sm font-medium transition-all duration-300',
        isOnline
          ? 'bg-green-50 border-b border-green-200 text-green-800'
          : 'bg-amber-50 border-b border-amber-200 text-amber-800',
      ].join(' ')}
      role="status"
      aria-live="polite"
      aria-label={isOnline ? 'Back online — syncing reports' : 'You are offline'}
    >
      {/* Network icon */}
      {isOnline ? (
        <Wifi
          size={16}
          className="text-green-600 flex-shrink-0"
          aria-hidden="true"
        />
      ) : (
        <WifiOff
          size={16}
          className="text-amber-600 flex-shrink-0"
          aria-hidden="true"
        />
      )}

      {/* Message */}
      <span className="flex-1 text-xs">
        {!isOnline && pendingCount === 0 &&
          "You're offline. New reports will be saved and uploaded when you reconnect."}
        {!isOnline && pendingCount > 0 &&
          `You're offline. ${pendingCount} report${pendingCount !== 1 ? 's' : ''} waiting to upload.`}
        {isOnline && pendingCount > 0 &&
          `Uploading ${pendingCount} saved report${pendingCount !== 1 ? 's' : ''}…`}
      </span>

      {/* Manual retry */}
      {isOnline && pendingCount > 0 && (
        <button
          onClick={syncDrafts}
          className="flex items-center gap-1 text-xs bg-green-600 text-white px-2.5 py-1 rounded-lg hover:bg-green-700 transition-colors"
          aria-label="Retry uploading pending reports"
        >
          <RefreshCw size={12} aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  );
}
