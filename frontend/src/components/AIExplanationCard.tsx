import { useState } from 'react';
import { Bot, ChevronDown, ChevronUp, Edit2, Check, X } from 'lucide-react';
import type { Issue, Category } from '@/types';
import api from '@/lib/api';

interface Props {
  issue: Issue;
  categories: Category[];
  onCorrectionApplied?: () => void;
  aiTimedOut?: boolean;
}

const CONFIDENCE_LABEL = (c: number): { text: string; color: string } => {
  if (c >= 0.85) return { text: 'High confidence', color: 'text-green-600' };
  if (c >= 0.60) return { text: 'Medium confidence', color: 'text-amber-600' };
  return { text: 'Low confidence', color: 'text-red-500' };
};

const SEVERITY_LABELS: Record<string, string> = {
  low: 'Low severity',
  medium: 'Medium severity',
  high: 'High severity',
  critical: '⚠️ Critical',
};

/**
 * AIExplanationCard
 *
 * Displays the AI-generated categorization result for a civic issue.
 * Shown on IssueDetailPage after the `ai_result` socket event fires
 * or after polling GET /ai/status/{id} returns a result.
 *
 * Features:
 * - Pending spinner when AI hasn't returned yet
 * - Collapsible card with category, confidence bar, explanation, severity
 * - Inline correction UI for RLHF-lite feedback (POST /ai/feedback)
 * - Accessible: ARIA roles, progressbar, aria-expanded, aria-live
 */
export default function AIExplanationCard({
  issue,
  categories,
  onCorrectionApplied,
  aiTimedOut = false,
}: Props) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [correctedCategory, setCorrectedCategory] = useState(issue.ai_category || '');
  const [correctedSeverity, setCorrectedSeverity] = useState(issue.ai_severity || 'medium');
  const [isSaving, setIsSaving] = useState(false);

  const handleSaveCorrection = async () => {
    if (!correctedCategory) return;
    setIsSaving(true);
    try {
      await api.post('/ai/feedback', {
        issue_id: issue.id,
        corrected_category: correctedCategory,
        corrected_severity: correctedSeverity,
      });
      setIsEditing(false);
      onCorrectionApplied?.();
    } catch {
      // Silent fail — correction is best-effort; the user has already helped
      // us by providing feedback even if the network call fails
    } finally {
      setIsSaving(false);
    }
  };

  // ── No AI result yet ───────────────────────────────────────
  if (!issue.ai_category && !issue.ai_confidence) {
    // Timed out — show fallback
    if (aiTimedOut) {
      return (
        <div
          className="bg-gray-50 border border-gray-200 rounded-xl p-3"
          role="status"
          aria-live="polite"
          aria-label="AI analysis unavailable"
        >
          <div className="flex items-start gap-3">
            <div className="text-gray-400 text-xl flex-shrink-0" aria-hidden="true">🤖</div>
            <div>
              <div className="text-sm font-medium text-gray-700">
                AI analysis unavailable
              </div>
              <div className="text-xs text-gray-500 mt-0.5">
                The AI service is temporarily busy. The category was not automatically detected.
              </div>
              {/* Show manual correction UI so user can still categorise */}
              <button
                onClick={() => setIsEditing(true)}
                className="mt-2 flex items-center gap-1 text-xs text-blue-600 font-medium"
                aria-label="Manually select the issue category"
              >
                Select category manually →
              </button>
            </div>
          </div>

          {/* Show the edit form if user clicked */}
          {isEditing && (
            <div className="mt-3 space-y-2 border-t border-gray-200 pt-3">
              <select
                value={correctedCategory}
                onChange={(e) => setCorrectedCategory(e.target.value)}
                className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white"
                aria-label="Select issue category"
              >
                <option value="">-- Select a category --</option>
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.name}>{cat.display_name}</option>
                ))}
              </select>
              <button
                onClick={handleSaveCorrection}
                disabled={!correctedCategory || isSaving}
                className="w-full bg-blue-600 text-white text-xs font-medium py-1.5 rounded-lg disabled:opacity-50"
              >
                {isSaving ? 'Saving…' : 'Save category'}
              </button>
            </div>
          )}
        </div>
      );
    }

    // Still pending
    return (
      <div
        className="bg-blue-50 rounded-xl p-3 flex items-center gap-3"
        role="status"
        aria-live="polite"
        aria-label="AI analysis in progress"
      >
        <div
          className="w-5 h-5 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin flex-shrink-0"
          aria-hidden="true"
        />
        <div>
          <div className="text-sm font-medium text-blue-800">
            AI is analysing your report…
          </div>
          <div className="text-xs text-blue-600">
            Category and severity will appear shortly
          </div>
        </div>
      </div>
    );
  }

  const confidence = issue.ai_confidence ?? 0;
  const confidenceInfo = CONFIDENCE_LABEL(confidence);
  const confidencePct = Math.round(confidence * 100);

  // Humanise the category name for display (e.g. "water_leakage" → "Water Leakage")
  const categoryDisplay = issue.ai_category
    ?.replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div
      className="bg-blue-50 border border-blue-100 rounded-xl overflow-hidden"
      role="region"
      aria-label="AI analysis result"
    >
      {/* ── Header — always visible ────────────────────── */}
      <button
        onClick={() => setIsExpanded((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-blue-100/50 transition-colors"
        aria-expanded={isExpanded}
        aria-controls="ai-explanation-body"
      >
        <Bot size={18} className="text-blue-600 flex-shrink-0" aria-hidden="true" />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-blue-900">
              AI detected: {categoryDisplay}
            </span>
            <span className={`text-xs font-medium ${confidenceInfo.color}`}>
              {confidencePct}% — {confidenceInfo.text}
            </span>
          </div>
          <div className="text-xs text-blue-600 mt-0.5 truncate">
            {issue.ai_summary || 'Tap to see AI reasoning'}
          </div>
        </div>

        {isExpanded ? (
          <ChevronUp size={16} className="text-blue-500 flex-shrink-0" aria-hidden="true" />
        ) : (
          <ChevronDown size={16} className="text-blue-500 flex-shrink-0" aria-hidden="true" />
        )}
      </button>

      {/* ── Expanded body ──────────────────────────────── */}
      {isExpanded && (
        <div id="ai-explanation-body" className="px-4 pb-4 space-y-3">

          {/* Confidence progress bar */}
          <div
            role="progressbar"
            aria-valuenow={confidencePct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`AI confidence: ${confidencePct}%`}
          >
            <div className="h-1.5 bg-blue-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  confidence >= 0.85
                    ? 'bg-green-500'
                    : confidence >= 0.60
                    ? 'bg-amber-500'
                    : 'bg-red-500'
                }`}
                style={{ width: `${confidencePct}%` }}
              />
            </div>
          </div>

          {/* AI explanation text */}
          {issue.ai_explanation && (
            <p className="text-xs text-blue-800 leading-relaxed">
              <span className="font-medium">Why: </span>
              {issue.ai_explanation}
            </p>
          )}

          {/* Reasoning — the model's step-by-step thinking */}
          {issue.ai_reasoning && (
            <div className="border-t border-blue-100 pt-2 mt-1">
              <details>
                <summary className="text-xs text-blue-600 font-medium cursor-pointer list-none flex items-center gap-1">
                  <span>▶</span>
                  <span>See AI reasoning</span>
                </summary>
                <p className="text-xs text-blue-700 mt-2 leading-relaxed italic">
                  "{issue.ai_reasoning}"
                </p>
              </details>
            </div>
          )}

          {/* Alternative categories considered */}
          {issue.ai_alternatives && Object.keys(issue.ai_alternatives).length > 0 && (
            <div className="text-xs text-blue-500 mt-1">
              <span className="font-medium">Also considered: </span>
              {Object.entries(issue.ai_alternatives)
                .sort(([, a], [, b]) => (b as number) - (a as number))
                .slice(0, 2)
                .map(([cat, conf]) => (
                  <span key={cat} className="mr-2">
                    {cat.replace('_', ' ')} ({Math.round((conf as number) * 100)}%)
                  </span>
                ))}
            </div>
          )}

          {/* Severity badge */}
          {issue.ai_severity && (
            <div className="flex items-center gap-2 text-xs text-blue-700">
              <span className="font-medium">Severity:</span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                issue.ai_severity === 'critical'
                  ? 'bg-red-100 text-red-700'
                  : issue.ai_severity === 'high'
                  ? 'bg-orange-100 text-orange-700'
                  : issue.ai_severity === 'medium'
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-green-100 text-green-700'
              }`}>
                {SEVERITY_LABELS[issue.ai_severity] || issue.ai_severity}
              </span>
            </div>
          )}

          {/* Correction trigger button */}
          {!issue.user_correction && !isEditing && (
            <button
              onClick={() => setIsEditing(true)}
              className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors"
              aria-label="Correct AI category suggestion"
            >
              <Edit2 size={12} aria-hidden="true" />
              Not right? Correct the AI
            </button>
          )}

          {/* Inline correction form */}
          {isEditing && (
            <div className="space-y-2 border-t border-blue-200 pt-3">
              <p className="text-xs text-blue-700 font-medium">
                You know your area best. Correct the AI if needed:
              </p>

              {/* Category selector */}
              <div>
                <label
                  htmlFor="ai-correct-category"
                  className="text-xs text-blue-600 block mb-1"
                >
                  Correct category
                </label>
                <select
                  id="ai-correct-category"
                  value={correctedCategory}
                  onChange={(e) => setCorrectedCategory(e.target.value)}
                  className="w-full text-xs border border-blue-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
                >
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.name}>
                      {cat.display_name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Severity selector */}
              <div>
                <label
                  htmlFor="ai-correct-severity"
                  className="text-xs text-blue-600 block mb-1"
                >
                  Correct severity
                </label>
                <select
                  id="ai-correct-severity"
                  value={correctedSeverity}
                  onChange={(e) => setCorrectedSeverity(e.target.value as 'low' | 'medium' | 'high' | 'critical')}
                  className="w-full text-xs border border-blue-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
                >
                  <option value="low">Low — minor inconvenience</option>
                  <option value="medium">Medium — significant issue</option>
                  <option value="high">High — dangerous or widespread</option>
                  <option value="critical">Critical — immediate safety risk</option>
                </select>
              </div>

              {/* Action buttons */}
              <div className="flex gap-2">
                <button
                  onClick={handleSaveCorrection}
                  disabled={isSaving || !correctedCategory}
                  className="flex items-center gap-1 bg-blue-600 text-white text-xs font-medium px-3 py-1.5 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  aria-label="Save AI correction"
                >
                  <Check size={12} aria-hidden="true" />
                  {isSaving ? 'Saving…' : 'Save correction'}
                </button>
                <button
                  onClick={() => setIsEditing(false)}
                  className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 px-2 transition-colors"
                  aria-label="Cancel correction"
                >
                  <X size={12} aria-hidden="true" />
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* User already corrected — thank you state */}
          {issue.user_correction && (
            <div className="flex items-center gap-1 text-xs text-green-600">
              <Check size={12} aria-hidden="true" />
              You corrected this AI suggestion. Thank you!
            </div>
          )}

          {/* Disclaimer */}
          <p className="text-xs text-blue-400 italic">
            AI analysis is a suggestion. Your knowledge of the area is the final authority.
          </p>
        </div>
      )}
    </div>
  );
}
