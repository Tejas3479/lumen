/**
 * ResolutionConfirmPanel
 *
 * Appears when an issue's status is "resolved".
 * Lets the community confirm the fix or dispute it with evidence.
 * Three disputes trigger automatic re-opening (handled server-side).
 */
import { useState } from 'react';
import { CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import { useIssuesApi } from '@/hooks/useApi';
import { useUserStore } from '@/store/userStore';

interface Props {
  issueId: string;
  onFeedbackSubmitted: (isResolved: boolean) => void;
}

export default function ResolutionConfirmPanel({
  issueId,
  onFeedbackSubmitted,
}: Props) {
  const { submitResolutionFeedback } = useIssuesApi();
  const { isAuthenticated } = useUserStore();

  const [selected, setSelected] = useState<boolean | null>(null);
  const [comment, setComment] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  // ── Post-submission confirmation ──────────────────────────────
  if (submitted) {
    return (
      <div
        className={[
          'rounded-xl p-4 flex items-center gap-3',
          selected
            ? 'bg-green-50 border border-green-200'
            : 'bg-amber-50 border border-amber-200',
        ].join(' ')}
        role="status"
        aria-live="polite"
      >
        {selected ? (
          <CheckCircle
            size={20}
            className="text-green-500 flex-shrink-0"
            aria-hidden="true"
          />
        ) : (
          <AlertTriangle
            size={20}
            className="text-amber-500 flex-shrink-0"
            aria-hidden="true"
          />
        )}
        <div className="text-sm">
          {selected ? (
            <>
              <strong className="text-green-800">Great!</strong>
              <span className="text-green-700">
                {' '}Thank you for confirming the fix.
              </span>
            </>
          ) : (
            <>
              <strong className="text-amber-800">Noted.</strong>
              <span className="text-amber-700">
                {' '}Your feedback has been recorded. We'll review the resolution.
              </span>
            </>
          )}
        </div>
      </div>
    );
  }

  // ── Submit handler ────────────────────────────────────────────
  const handleSubmit = async () => {
    if (selected === null) return;
    // Dispute requires an explanatory comment
    if (!selected && !comment.trim()) return;

    setIsSubmitting(true);
    try {
      const ok = await submitResolutionFeedback(
        issueId,
        selected,
        comment.trim() || undefined,
      );
      if (ok) {
        setSubmitted(true);
        onFeedbackSubmitted(selected);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // ── Main UI ───────────────────────────────────────────────────
  return (
    <div
      className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-4"
      role="region"
      aria-label="Resolution confirmation"
    >
      {/* Header */}
      <div>
        <h3 className="text-sm font-semibold text-amber-900">
          🏁 The authorities say this is fixed. Is it actually resolved?
        </h3>
        <p className="text-xs text-amber-700 mt-1">
          Your confirmation helps us track real outcomes — not just official
          closures. 3 disputes will automatically reopen this issue.
        </p>
      </div>

      {/* Yes / No selection */}
      <div className="grid grid-cols-2 gap-3">
        {/* Confirm resolved */}
        <button
          onClick={() => {
            setSelected(true);
            setComment('');
          }}
          className={[
            'flex flex-col items-center gap-2 p-3 rounded-xl border-2 transition-all',
            selected === true
              ? 'border-green-500 bg-green-50'
              : 'border-gray-200 hover:border-green-300 hover:bg-green-50',
          ].join(' ')}
          aria-pressed={selected === true}
          aria-label="Yes, the issue is fixed"
        >
          <CheckCircle
            size={24}
            className={selected === true ? 'text-green-500' : 'text-gray-300'}
            aria-hidden="true"
          />
          <div className="text-center">
            <div className="text-sm font-semibold text-gray-800">
              Yes, it's fixed
            </div>
            <div className="text-xs text-gray-500">
              I can confirm the issue is resolved
            </div>
          </div>
        </button>

        {/* Dispute resolution */}
        <button
          onClick={() => setSelected(false)}
          className={[
            'flex flex-col items-center gap-2 p-3 rounded-xl border-2 transition-all',
            selected === false
              ? 'border-red-500 bg-red-50'
              : 'border-gray-200 hover:border-red-300 hover:bg-red-50',
          ].join(' ')}
          aria-pressed={selected === false}
          aria-label="No, the issue is still a problem"
        >
          <XCircle
            size={24}
            className={selected === false ? 'text-red-500' : 'text-gray-300'}
            aria-hidden="true"
          />
          <div className="text-center">
            <div className="text-sm font-semibold text-gray-800">
              No, still a problem
            </div>
            <div className="text-xs text-gray-500">
              The issue has not been fixed
            </div>
          </div>
        </button>
      </div>

      {/* Required dispute comment */}
      {selected === false && (
        <div>
          <label
            htmlFor="dispute-comment"
            className="text-xs font-medium text-gray-700 block mb-1"
          >
            What's still wrong?{' '}
            <span className="text-red-500" aria-hidden="true">*</span>
          </label>
          <textarea
            id="dispute-comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Tell us what's still wrong — e.g. 'The pothole was patched but the patch has already broken'"
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-red-400 resize-none"
            aria-required="true"
            aria-describedby="dispute-hint"
          />
          <p id="dispute-hint" className="text-xs text-gray-400 mt-1">
            Required — helps officials understand what needs attention
          </p>
        </div>
      )}

      {/* Submit button — appears only after a choice is made */}
      {selected !== null && (
        <button
          onClick={handleSubmit}
          disabled={
            isSubmitting ||
            (selected === false && !comment.trim()) ||
            !isAuthenticated
          }
          className={[
            'w-full py-3 rounded-xl text-sm font-semibold transition-all',
            selected
              ? 'bg-green-600 hover:bg-green-700 text-white'
              : 'bg-red-600 hover:bg-red-700 text-white',
            'disabled:opacity-50 disabled:cursor-not-allowed',
          ].join(' ')}
          aria-label={selected ? 'Confirm resolution' : 'Submit dispute'}
        >
          {isSubmitting
            ? 'Submitting…'
            : selected
            ? "✓ Confirm — it's fixed"
            : '✗ Submit dispute'}
        </button>
      )}

      {/* Auth prompt for unauthenticated visitors */}
      {!isAuthenticated && (
        <p className="text-xs text-center text-gray-400">
          Sign in to confirm or dispute resolutions
        </p>
      )}
    </div>
  );
}
