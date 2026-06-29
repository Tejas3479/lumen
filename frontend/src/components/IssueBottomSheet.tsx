/**
 * IssueBottomSheet — slide-up preview card shown when a map marker is tapped.
 *
 * Accessibility:
 *  - role="dialog" + aria-modal="true" for screen readers
 *  - Focus trapped inside the sheet on mount
 *  - Escape key closes the sheet
 *  - aria-live="assertive" on the emergency banner
 *
 * Navigation:
 *  - "View Full Details" navigates to /issues/{id} (IssueDetailPage — Session 11)
 */
import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  X, MapPin, ThumbsUp, CheckCircle, AlertTriangle, ChevronRight, Eye,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import type { Issue } from '@/types';
import { useVerificationApi } from '@/hooks/useApi';
import { useUserStore } from '@/store/userStore';
import { useGeolocation } from '@/hooks/useGeolocation';

// ── Status display config ────────────────────────────────────
const STATUS_LABELS: Record<string, string> = {
  reported:    'Reported',
  verified:    'Verified',
  assigned:    'Assigned',
  in_progress: 'In Progress',
  resolved:    'Resolved',
  disputed:    'Disputed',
  closed:      'Closed',
};

const STATUS_COLORS: Record<string, string> = {
  reported:    'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300',
  verified:    'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  assigned:    'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  in_progress: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  resolved:    'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  disputed:    'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  closed:      'bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
};

const SEVERITY_COLORS: Record<string, string> = {
  low:      'bg-emerald-100 text-emerald-700',
  medium:   'bg-amber-100   text-amber-700',
  high:     'bg-orange-100  text-orange-700',
  critical: 'bg-red-100     text-red-700',
};

// ── Props ────────────────────────────────────────────────────
interface Props {
  issue: Issue;
  onClose: () => void;
}

// ── Component ────────────────────────────────────────────────
export default function IssueBottomSheet({ issue, onClose }: Props) {
  const navigate  = useNavigate();
  const sheetRef  = useRef<HTMLDivElement>(null);

  // Verification hooks
  const { verifyIssue } = useVerificationApi();
  const isAuthenticated = useUserStore((s) => s.isAuthenticated);
  const { location } = useGeolocation();
  const [verified, setVerified] = useState(false);

  // Close on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  // Trap focus on mount
  useEffect(() => {
    sheetRef.current?.focus();
  }, []);

  const thumbnail =
    issue.media?.[0]?.thumbnail_path ??
    issue.media?.[0]?.file_path;

  const timeAgo = formatDistanceToNow(new Date(issue.created_at), { addSuffix: true });

  const handleViewDetails = () => {
    onClose();
    navigate(`/issues/${issue.id}`);
  };

  return (
    <>
      {/* ── Backdrop ──────────────────────────────────────── */}
      <div
        className="fixed inset-0 bg-black/30 backdrop-blur-[1px] z-30"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* ── Sheet ─────────────────────────────────────────── */}
      <div
        ref={sheetRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={`Issue details: ${issue.title}`}
        className="
          fixed bottom-0 left-0 right-0 z-40
          bg-white dark:bg-gray-900
          rounded-t-3xl shadow-2xl
          max-h-[75vh] overflow-y-auto
          outline-none
        "
        style={{ animation: 'slideUp 0.28s cubic-bezier(0.32,0.72,0,1)' }}
      >
        {/* Drag handle + close button */}
        <div className="flex items-center justify-between px-4 pt-3 pb-2">
          <div className="flex-1" />
          <div
            className="w-10 h-1 bg-gray-300 dark:bg-gray-600 rounded-full"
            aria-hidden="true"
          />
          <div className="flex-1 flex justify-end">
            <button
              onClick={onClose}
              className="p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              aria-label="Close issue preview"
            >
              <X size={17} className="text-gray-500" />
            </button>
          </div>
        </div>

        <div className="px-4 pb-6 space-y-3.5">
          {/* ── Emergency banner ────────────────────────── */}
          {issue.is_emergency && (
            <div
              className="flex items-center gap-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-2xl px-3 py-2"
              role="alert"
              aria-live="assertive"
            >
              <AlertTriangle
                size={15}
                className="text-red-500 flex-shrink-0"
                style={{ animation: 'pulse 1.4s ease-in-out infinite' }}
                aria-hidden="true"
              />
              <span className="text-sm font-semibold text-red-700 dark:text-red-400">
                Emergency Issue — Officials Notified
              </span>
            </div>
          )}

          {/* ── Photo + header info ──────────────────────── */}
          <div className="flex gap-3">
            {thumbnail && (
              <img
                src={`/media/${thumbnail}`}
                alt={`Photo of: ${issue.title}`}
                className="w-20 h-20 rounded-2xl object-cover flex-shrink-0 bg-gray-100"
                loading="lazy"
              />
            )}
            <div className="flex-1 min-w-0">
              {/* Badges row */}
              <div className="flex items-center gap-1.5 flex-wrap mb-1.5">
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${STATUS_COLORS[issue.status] ?? STATUS_COLORS['reported']}`}>
                  {STATUS_LABELS[issue.status] ?? issue.status}
                </span>
                {issue.severity && issue.severity !== 'medium' && (
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full capitalize ${SEVERITY_COLORS[issue.severity] ?? ''}`}>
                    {issue.severity}
                  </span>
                )}
                {issue.category?.display_name && (
                  <span className="text-[10px] text-gray-500 dark:text-gray-400 capitalize">
                    {issue.category.display_name}
                  </span>
                )}
              </div>

              {/* Title */}
              <h3 className="font-semibold text-gray-900 dark:text-white text-sm leading-snug line-clamp-3">
                {issue.title}
              </h3>
            </div>
          </div>

          {/* ── Location + time ──────────────────────────── */}
          <div className="flex items-start gap-1.5 text-xs text-gray-500 dark:text-gray-400">
            <MapPin size={12} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
            <span className="line-clamp-2 flex-1">
              {issue.address
                ?? issue.ward
                ?? `${issue.latitude.toFixed(4)}, ${issue.longitude.toFixed(4)}`}
            </span>
            <span className="flex-shrink-0 text-gray-400 ml-1">· {timeAgo}</span>
          </div>

          {/* ── AI Summary ───────────────────────────────── */}
          {issue.ai_summary && (
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-2xl p-3 text-xs text-blue-800 dark:text-blue-300">
              <span className="font-semibold">AI: </span>
              {issue.ai_summary}
              {issue.ai_confidence != null && (
                <span className="ml-1 text-blue-500">
                  ({Math.round(issue.ai_confidence * 100)}% confidence)
                </span>
              )}
            </div>
          )}

          {/* ── Stats row ────────────────────────────────── */}
          <div
            className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400"
            aria-label="Issue statistics"
          >
            <span className="flex items-center gap-1">
              <ThumbsUp size={12} aria-hidden="true" />
              <span aria-label={`${issue.vote_count} people support this issue`}>
                {issue.vote_count} supporting
              </span>
            </span>
            <span className="flex items-center gap-1">
              <CheckCircle size={12} aria-hidden="true" />
              <span aria-label={`${issue.verification_count} verifications`}>
                {issue.verification_count} verified
              </span>
            </span>
            <span className="flex items-center gap-1 ml-auto">
              <Eye size={12} aria-hidden="true" />
              <span aria-label={`${issue.view_count} views`}>
                {issue.view_count}
              </span>
            </span>
          </div>

          {/* ── Quick Verify CTAs ────────────────── */}
          {issue.status !== 'resolved' && issue.status !== 'closed' && !verified && (
            <div className="flex gap-2">
              {/* Soft verify */}
              <button
                id={`sheet-soft-verify-${issue.id}`}
                onClick={async () => {
                  const ok = await verifyIssue(issue.id, 'soft');
                  if (ok) setVerified(true);
                }}
                disabled={!isAuthenticated}
                className="flex-1 flex items-center justify-center gap-1.5 py-2.5 border border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-400 rounded-xl text-xs font-medium hover:bg-blue-50 dark:hover:bg-blue-900/20 disabled:opacity-50 transition-colors"
                aria-label="Confirm this issue exists from personal knowledge (soft verification)"
              >
                <Eye size={14} aria-hidden="true" />
                I know this exists
              </button>

              {/* Hard verify — only shown when GPS is available */}
              {location && (
                <button
                  id={`sheet-hard-verify-${issue.id}`}
                  onClick={async () => {
                    const ok = await verifyIssue(
                      issue.id, 'hard',
                      location.latitude, location.longitude,
                    );
                    if (ok) setVerified(true);
                  }}
                  disabled={!isAuthenticated}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-blue-600 text-white rounded-xl text-xs font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
                  aria-label="Hard-verify — I am at this location right now"
                >
                  <MapPin size={14} aria-hidden="true" />
                  I'm here now
                </button>
              )}
            </div>
          )}

          {/* Success banner after verification */}
          {verified && (
            <div
              className="flex items-center justify-center gap-2 py-2 text-green-700 dark:text-green-400 text-xs font-medium"
              role="status"
              aria-live="polite"
            >
              <CheckCircle size={14} aria-hidden="true" />
              Verification recorded — thank you!
            </div>
          )}

          {/* ── CTA ──────────────────────────────────────── */}
          <button
            id={`issue-sheet-details-${issue.id}`}
            onClick={handleViewDetails}
            className="
              w-full flex items-center justify-between
              bg-gradient-to-r from-primary-600 to-violet-600
              hover:from-primary-700 hover:to-violet-700
              text-white text-sm font-semibold
              px-4 py-3.5 rounded-2xl
              transition-all duration-200
              active:scale-[0.98]
            "
            aria-label={`View full details for: ${issue.title}`}
          >
            <span>View Full Details & Timeline</span>
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </div>
      </div>

      <style>{`
        @keyframes slideUp {
          from { transform: translateY(100%); opacity: 0.6; }
          to   { transform: translateY(0);    opacity: 1;   }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.4; }
        }
      `}</style>
    </>
  );
}
