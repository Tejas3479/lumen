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
import { useEffect } from 'react';
import { Wifi, WifiOff, RefreshCw } from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import { useOfflineQueue } from '@/hooks/useOfflineQueue';

export default function OfflineSyncBanner() {
  const isOnline      = useAppStore((s) => s.isOnline);
  const pendingDrafts = useAppStore((s) => s.pendingDrafts);
  const { syncQueue } = useOfflineQueue();

  const pendingCount = pendingDrafts.filter(
    (d) => d.sync_status === 'pending'
  ).length;

  // ── Auto-sync on reconnect ──────────────────────────────────────
  useEffect(() => {
    if (isOnline && pendingCount > 0) {
      syncQueue();
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
          onClick={syncQueue}
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
