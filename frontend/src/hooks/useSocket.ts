/**
 * useSocket — Global Socket.IO event handler.
 *
 * Wires all 13 Lumen socket events to the appropriate Zustand store
 * actions and toast notifications.
 *
 * Mount once at the root (App.tsx). Uses a ref guard so that
 * re-renders do not register duplicate listeners.
 *
 * Event → Store mapping:
 *   new_issue                   → issueStore.addIssueFromSocket
 *   issue_updated               → issueStore.updateIssue
 *   status_update               → issueStore.updateIssueStatusFromSocket + toast
 *   ai_result                   → issueStore.updateAIResult + toast if viewing
 *   verification_update         → issueStore.updateVerification
 *   comment_added               → DOM event (IssueDetailPage listens)
 *   leaderboard_update          → DOM event (LeaderboardPage listens)
 *   emergency_alert             → issueStore.addIssueFromSocket + urgent toast
 *   issue_reopened              → issueStore.updateIssueStatusFromSocket + toast
 *   resolution_feedback_received→ DOM event
 *   offline_sync_completed      → appStore.removePendingDraft + toast
 *   admin_action                → DOM event (AdminDashboardPage listens)
 *   hotspot_update              → DOM event (PredictivePage listens)
 *   gamification_event          → userStore.updateUser + DOM event → GamificationToast
 */
import { useEffect, useRef } from 'react';
import { connectSocket, getSocket } from '@/lib/socket';
import { useIssueStore } from '@/store/issueStore';
import { useAppStore } from '@/store/appStore';
import { useUserStore } from '@/store/userStore';
import toast from 'react-hot-toast';
import type { Issue, StatusHistoryEntry } from '@/types';

// ── Payload shapes ────────────────────────────────────────────────

interface SocketCommentAdded {
  issue_id: string;
  comment: {
    id: string;
    content: string;
    is_official: boolean;
    display_name: string;
    created_at: string;
  };
}

interface SocketLeaderboardUpdate {
  top_users: Array<{
    user_id: string;
    display_name: string;
    points: number;
    rank: number;
  }>;
}

interface SocketGamificationEvent {
  action: string;
  points_awarded: number;
  total_points: number;
  badge_unlocked: { name: string; display_name: string; icon: string } | null;
  new_level: number | null;
}

interface SocketHotspotUpdate {
  hotspots: Array<{
    id: string;
    category: string;
    center_latitude: number;
    center_longitude: number;
    radius_meters: number;
    confidence: number;
  }>;
}

interface SocketOfflineSyncCompleted {
  synced: Array<{ key: string; issue_id: string }>;
  skipped: Array<{ key: string; issue_id: string }>;
}

interface SocketAIResult {
  issue_id: string;
  ai_category: string;
  ai_severity: Issue['ai_severity'];
  ai_confidence: number;
  ai_explanation: string;
  ai_summary: string;
  ai_reasoning: string | null;
  ai_alternatives: Record<string, number> | null;
}

// ── Status label map ──────────────────────────────────────────────
const STATUS_TOAST_LABELS: Partial<Record<Issue['status'], string>> = {
  verified:    '✓ Issue verified by the community',
  assigned:    '→ Issue assigned to a team',
  in_progress: '🔧 Work has started on this issue',
  resolved:    '✅ Officials say this is resolved',
  disputed:    '⚠️ Resolution disputed — issue reopened',
  closed:      'Issue has been closed',
};

// ── Hook ──────────────────────────────────────────────────────────
export function useSocket() {
  const initialized = useRef(false);

  // Store selectors — pulled once at mount to avoid stale closures
  const addIssueFromSocket        = useIssueStore((s) => s.addIssueFromSocket);
  const updateIssue               = useIssueStore((s) => s.updateIssue);
  const updateIssueStatusFromSocket = useIssueStore((s) => s.updateIssueStatusFromSocket);
  const updateAIResult            = useIssueStore((s) => s.updateAIResult);
  const updateVerification        = useIssueStore((s) => s.updateVerification);

  const setOnline                 = useAppStore((s) => s.setOnline);
  const setSocketConnected        = useAppStore((s) => s.setSocketConnected);
  const removePendingDraft        = useAppStore((s) => s.removePendingDraft);

  const updateUser                = useUserStore((s) => s.updateUser);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    const handleOnline = () => {
      setOnline(true);
    };

    const handleOffline = () => {
      setOnline(false);
      setSocketConnected(false);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    setOnline(navigator.onLine);

    const socket = getSocket();
    connectSocket();

    // ── Connection lifecycle ────────────────────────────────────
    socket.on('connect', () => {
      setSocketConnected(true);
      setOnline(true);
    });

    socket.on('disconnect', () => {
      setSocketConnected(false);
    });

    socket.on('connect_error', () => {
      setSocketConnected(false);
    });

    // ── Event 1: new_issue ──────────────────────────────────────
    // A citizen has submitted a new issue — add it to the map.
    socket.on('new_issue', (data: Issue) => {
      addIssueFromSocket(data);
      if (data.is_emergency) {
        toast.error(`🚨 Emergency reported: ${data.title}`, {
          duration: 8000,
          id: `emergency-${data.id}`,
        });
      }
    });

    // ── Event 2: issue_updated ──────────────────────────────────
    // Arbitrary field patch (e.g. admin edit). Merge into store.
    socket.on(
      'issue_updated',
      (data: { issue_id: string; updates: Partial<Issue> }) => {
        updateIssue(data.issue_id, data.updates);
      }
    );

    // ── Event 3: status_update ──────────────────────────────────
    // An issue has moved through the lifecycle (verified → resolved etc.)
    socket.on(
      'status_update',
      (data: {
        issue_id: string;
        new_status: Issue['status'];
        history_entry: StatusHistoryEntry;
      }) => {
        updateIssueStatusFromSocket(
          data.issue_id,
          data.new_status,
          data.history_entry
        );
        // Show a toast when the user has this issue open
        const selected = useIssueStore.getState().selectedIssue;
        if (selected?.id === data.issue_id) {
          const label = STATUS_TOAST_LABELS[data.new_status];
          if (label) toast.success(label, { duration: 5000 });
        }
      }
    );

    // ── Event 4: ai_result ──────────────────────────────────────
    // Celery worker finished AI categorisation — patch the issue.
    socket.on('ai_result', (data: SocketAIResult) => {
      updateAIResult(data.issue_id, {
        ai_category:    data.ai_category,
        ai_severity:    data.ai_severity,
        ai_confidence:  data.ai_confidence,
        ai_explanation: data.ai_explanation,
        ai_summary:     data.ai_summary,
        ai_reasoning:   data.ai_reasoning,
        ai_alternatives: data.ai_alternatives,
      });
      // Toast if the user is currently viewing this issue
      const selected = useIssueStore.getState().selectedIssue;
      if (selected?.id === data.issue_id) {
        const pct = Math.round(data.ai_confidence * 100);
        toast.success(
          `🤖 AI identified: ${data.ai_category.replace(/_/g, ' ')} (${pct}% confidence)`,
          { duration: 4000, id: `ai-${data.issue_id}` }
        );
      }
    });

    // ── Event 5: verification_update ────────────────────────────
    // Community verification count changed.
    socket.on(
      'verification_update',
      (data: { issue_id: string; verification_count: number }) => {
        updateVerification(data.issue_id, data.verification_count);
      }
    );

    // ── Event 6: comment_added ──────────────────────────────────
    // A new comment arrived. IssueDetailPage listens via DOM event
    // (avoids prop-drilling and keeps this hook store-agnostic).
    socket.on('comment_added', (data: SocketCommentAdded) => {
      window.dispatchEvent(
        new CustomEvent('lumen:comment_added', { detail: data })
      );
    });

    // ── Event 7: leaderboard_update ─────────────────────────────
    // Top-20 ranking changed. LeaderboardPage listens via DOM event.
    socket.on('leaderboard_update', (data: SocketLeaderboardUpdate) => {
      window.dispatchEvent(
        new CustomEvent('lumen:leaderboard_update', { detail: data })
      );
    });

    // ── Event 8: emergency_alert ────────────────────────────────
    // High-priority broadcast — appears prominently for all users.
    socket.on('emergency_alert', (data: Issue) => {
      addIssueFromSocket({ ...data, is_emergency: true });
      toast.error(`🚨 EMERGENCY: ${data.title}`, {
        duration: 10000,
        id: `emergency-${data.id}`,
        style: {
          background: '#FEE2E2',
          color: '#991B1B',
          fontWeight: 'bold',
          border: '2px solid #EF4444',
        },
      });
    });

    // ── Event 9: issue_reopened ─────────────────────────────────
    // 3 disputes triggered automatic reopen.
    socket.on(
      'issue_reopened',
      (data: { issue_id: string; dispute_count: number }) => {
        updateIssueStatusFromSocket(data.issue_id, 'disputed', null);
        const selected = useIssueStore.getState().selectedIssue;
        if (selected?.id === data.issue_id) {
          toast(`⚠️ Issue reopened after ${data.dispute_count} disputes`, {
            duration: 6000,
            icon: '⚠️',
          });
        }
      }
    );

    // ── Event 10: resolution_feedback_received ──────────────────
    // Dispatched as DOM event; UI already handles optimistic state.
    socket.on(
      'resolution_feedback_received',
      (data: { issue_id: string; feedback: { is_resolved: boolean } }) => {
        window.dispatchEvent(
          new CustomEvent('lumen:resolution_feedback', { detail: data })
        );
      }
    );

    // ── Event 11: offline_sync_completed ────────────────────────
    // Celery uploaded offline drafts — remove from pending queue.
    socket.on('offline_sync_completed', (data: SocketOfflineSyncCompleted) => {
      data.synced.forEach((item) => {
        removePendingDraft(item.key);
        toast.success(
          `Report uploaded: ${item.issue_id.slice(0, 8)}…`,
          { duration: 3000 }
        );
      });
    });

    // ── Event 12: admin_action ──────────────────────────────────
    // Relevant only on AdminDashboardPage — forward via DOM.
    socket.on(
      'admin_action',
      (data: { action: string; target_id: string; actor_id: string }) => {
        window.dispatchEvent(
          new CustomEvent('lumen:admin_action', { detail: data })
        );
      }
    );

    // ── Event 13: hotspot_update ────────────────────────────────
    // Updated predictive hotspots — PredictivePage subscribes.
    socket.on('hotspot_update', (data: SocketHotspotUpdate) => {
      window.dispatchEvent(
        new CustomEvent('lumen:hotspot_update', { detail: data })
      );
    });

    // ── Gamification events ─────────────────────────────────────
    // Points/badges awarded. Update store + dispatch for GamificationToast.
    socket.on('gamification_event', (data: SocketGamificationEvent) => {
      const currentUser = useUserStore.getState().user;
      if (currentUser && data.total_points !== undefined) {
        updateUser({
          points: data.total_points,
          ...(data.new_level !== null ? { level: data.new_level } : {}),
        });
      }
      window.dispatchEvent(
        new CustomEvent('lumen:gamification_event', { detail: data })
      );
    });

    // ── Cleanup ─────────────────────────────────────────────────
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      socket.off('connect');
      socket.off('disconnect');
      socket.off('connect_error');
      socket.off('new_issue');
      socket.off('issue_updated');
      socket.off('status_update');
      socket.off('ai_result');
      socket.off('verification_update');
      socket.off('comment_added');
      socket.off('leaderboard_update');
      socket.off('emergency_alert');
      socket.off('issue_reopened');
      socket.off('resolution_feedback_received');
      socket.off('offline_sync_completed');
      socket.off('admin_action');
      socket.off('hotspot_update');
      socket.off('gamification_event');
      initialized.current = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Expose emit/on helpers for ad-hoc use by individual components
  const emit = (event: string, data?: unknown) => getSocket().emit(event, data);
  const on   = <T = unknown>(event: string, handler: (data: T) => void) => {
    const socket = getSocket();
    socket.on(event, handler);
    return () => { socket.off(event, handler); };
  };

  return { emit, on };
}
