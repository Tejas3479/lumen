/**
 * VerificationPanel — shown on Issue Detail page.
 *
 * Allows authenticated users to confirm an issue either by:
 *   - Hard verification: using their GPS to prove proximity (≤ 100m)
 *   - Soft verification: confirming from personal knowledge (no location needed)
 *
 * Visual states:
 *   1. Loading  — spinner while the API call is in-flight
 *   2. Success  — green confirmation card (replaces the panel permanently)
 *   3. Error    — red inline error with the server's message
 *   4. Default  — two option buttons with accessibility labels
 *
 * Accessibility:
 *   - role="region" on container, aria-label="Issue verification"
 *   - role="alert" + aria-live="assertive" on errors
 *   - role="status" + aria-live="polite" on success banner
 *   - All interactive elements have descriptive aria-label attributes
 */
import { useState } from 'react';
import { CheckCircle, MapPin, Eye, Loader2 } from 'lucide-react';
import api from '@/lib/api';
import { useGeolocation } from '@/hooks/useGeolocation';
import { useUserStore } from '@/store/userStore';
import type { Issue } from '@/types';

// ── Props ────────────────────────────────────────────────────

interface Props {
  issue: Issue;
  onVerified: (newCount: number) => void;
}

// ── Component ────────────────────────────────────────────────

export default function VerificationPanel({ issue, onVerified }: Props) {
  const { location } = useGeolocation();
  const isAuthenticated = useUserStore((s) => s.isAuthenticated);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Don't render for terminal-state issues
  if (issue.status === 'resolved' || issue.status === 'closed') {
    return null;
  }

  // ── Post-verification success state ──────────────────────
  if (verified) {
    return (
      <div
        className="flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl px-4 py-3"
        role="status"
        aria-live="polite"
      >
        <CheckCircle size={20} className="text-green-500 flex-shrink-0" aria-hidden="true" />
        <div>
          <div className="text-sm font-semibold text-green-800">Thank you for verifying!</div>
          <div className="text-xs text-green-600 mt-0.5">
            Your confirmation helps officials prioritise this issue faster.
          </div>
        </div>
      </div>
    );
  }

  // ── Verification handler ──────────────────────────────────
  const handleVerify = async (type: 'hard' | 'soft') => {
    if (!isAuthenticated) {
      setError('Please sign in to verify issues');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const body: Record<string, unknown> = { verification_type: type };
      if (type === 'hard' && location) {
        body.latitude = location.latitude;
        body.longitude = location.longitude;
      }

      await api.post(`/issues/${issue.id}/verify`, body);
      setVerified(true);
      onVerified((issue.verification_count ?? 0) + 1);
    } catch (err: any) {
      const msg =
        err?.response?.data?.message ||
        err?.response?.data?.detail?.message ||
        'Verification failed. Please try again.';
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const canHardVerify = !!location;

  return (
    <div
      className="bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 space-y-3"
      role="region"
      aria-label="Issue verification"
    >
      {/* Header */}
      <div>
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
          Can you confirm this issue?
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {issue.verification_count ?? 0} citizen
          {(issue.verification_count ?? 0) !== 1 ? 's have' : ' has'} already confirmed this.
        </p>
      </div>

      {/* Error message */}
      {error && (
        <div
          className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2"
          role="alert"
          aria-live="assertive"
        >
          {error}
        </div>
      )}

      {/* Verification option buttons */}
      <div className="space-y-2">

        {/* Hard verification — requires GPS */}
        <button
          id={`verify-hard-${issue.id}`}
          onClick={() => handleVerify('hard')}
          disabled={isSubmitting || !canHardVerify || !isAuthenticated}
          className={[
            'w-full flex items-start gap-3 p-3 rounded-xl border-2 text-left transition-all duration-150',
            canHardVerify && isAuthenticated
              ? 'border-blue-200 hover:border-blue-400 hover:bg-blue-50 dark:border-blue-800 dark:hover:border-blue-600 dark:hover:bg-blue-900/20 cursor-pointer'
              : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 cursor-not-allowed opacity-60',
          ].join(' ')}
          aria-label="Verify this issue — I am at the location right now (hard verification)"
          aria-disabled={isSubmitting || !canHardVerify || !isAuthenticated}
        >
          {isSubmitting ? (
            <Loader2
              size={18}
              className="text-blue-500 animate-spin flex-shrink-0 mt-0.5"
              aria-hidden="true"
            />
          ) : (
            <MapPin
              size={18}
              className="text-blue-500 flex-shrink-0 mt-0.5"
              aria-hidden="true"
            />
          )}
          <div>
            <div className="text-sm font-medium text-gray-800 dark:text-gray-100">
              I'm here right now ✓
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {canHardVerify
                ? "Uses your GPS to confirm you're at the location (strongest signal, 25 pts)"
                : 'Enable location access to use this option'}
            </div>
          </div>
        </button>

        {/* Soft verification — no location needed */}
        <button
          id={`verify-soft-${issue.id}`}
          onClick={() => handleVerify('soft')}
          disabled={isSubmitting || !isAuthenticated}
          className={[
            'w-full flex items-start gap-3 p-3 rounded-xl border-2 text-left transition-all duration-150',
            isAuthenticated
              ? 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer'
              : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 cursor-not-allowed opacity-60',
          ].join(' ')}
          aria-label="Soft-verify — I know this issue exists from personal knowledge"
          aria-disabled={isSubmitting || !isAuthenticated}
        >
          {isSubmitting ? (
            <Loader2
              size={18}
              className="text-gray-400 animate-spin flex-shrink-0 mt-0.5"
              aria-hidden="true"
            />
          ) : (
            <Eye
              size={18}
              className="text-gray-400 dark:text-gray-500 flex-shrink-0 mt-0.5"
              aria-hidden="true"
            />
          )}
          <div>
            <div className="text-sm font-medium text-gray-800 dark:text-gray-100">
              I know this exists ✓
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Confirm from personal knowledge — no location needed (10 pts)
            </div>
          </div>
        </button>
      </div>

      {/* Sign-in nudge for unauthenticated users */}
      {!isAuthenticated && (
        <p className="text-xs text-center text-gray-400 dark:text-gray-500">
          Sign in to verify issues and earn points
        </p>
      )}
    </div>
  );
}
