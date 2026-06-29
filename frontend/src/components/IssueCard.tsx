/**
 * IssueCard — compact card for issue lists and feed.
 * Shows severity badge, category icon, status chip, vote count, and distance.
 */
import type { Issue } from '@/types';

interface Props {
  issue: Issue;
  onClick?: () => void;
  showDistance?: boolean;
}

const SEVERITY_STYLES: Record<string, string> = {
  low:      'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  medium:   'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  high:     'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  critical: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};

const STATUS_STYLES: Record<string, string> = {
  reported:    'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  verified:    'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  assigned:    'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  in_progress: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
  resolved:    'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  disputed:    'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  closed:      'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500',
};

const STATUS_LABEL: Record<string, string> = {
  reported:    'Reported',
  verified:    'Verified',
  assigned:    'Assigned',
  in_progress: 'In Progress',
  resolved:    'Resolved ✓',
  disputed:    'Disputed',
  closed:      'Closed',
};

const CATEGORY_EMOJI: Record<string, string> = {
  pothole:       '🕳️',
  water_leakage: '💧',
  streetlight:   '💡',
  garbage:       '🗑️',
  drainage:      '🌊',
  road_damage:   '🚧',
  tree_hazard:   '🌳',
  vandalism:     '✏️',
  noise:         '🔊',
  other:         '⚠️',
};

function formatDistance(meters?: number): string {
  if (meters === undefined || meters === null) return '';
  if (meters < 1000) return `${Math.round(meters)}m away`;
  return `${(meters / 1000).toFixed(1)}km away`;
}

function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const seconds = Math.floor((now - then) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export default function IssueCard({ issue, onClick, showDistance = false }: Props) {
  const categoryName = issue.category?.name ?? issue.ai_category ?? 'other';
  const emoji = CATEGORY_EMOJI[categoryName] ?? '⚠️';
  const dist = (issue as any).distance_meters;

  return (
    <button
      onClick={onClick}
      className="w-full text-left group"
      aria-label={`View issue: ${issue.title}`}
    >
      <div className="card p-4 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 cursor-pointer border border-transparent hover:border-primary-200 dark:hover:border-primary-700">
        {/* Emergency banner */}
        {issue.is_emergency && (
          <div className="flex items-center gap-1.5 mb-2.5 text-red-600 dark:text-red-400">
            <span className="text-sm animate-pulse">🚨</span>
            <span className="text-xs font-bold uppercase tracking-wide">Emergency</span>
          </div>
        )}

        {/* Header row */}
        <div className="flex items-start gap-3">
          {/* Category emoji */}
          <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-primary-50 dark:bg-primary-900/30 flex items-center justify-center text-xl">
            {emoji}
          </div>

          <div className="flex-1 min-w-0">
            {/* Title */}
            <p className="font-semibold text-slate-900 dark:text-white text-sm leading-snug truncate group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
              {issue.title}
            </p>

            {/* Meta row */}
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {/* Severity badge */}
              <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-md ${SEVERITY_STYLES[issue.severity] ?? SEVERITY_STYLES.medium}`}>
                {issue.severity}
              </span>

              {/* Status chip */}
              <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-md ${STATUS_STYLES[issue.status] ?? STATUS_STYLES.reported}`}>
                {STATUS_LABEL[issue.status] ?? issue.status}
              </span>

              {/* Category name */}
              {issue.category?.display_name && (
                <span className="text-[10px] text-slate-400 dark:text-slate-500">
                  {issue.category.display_name}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Description snippet */}
        {issue.description && (
          <p className="mt-2.5 text-xs text-slate-500 dark:text-slate-400 line-clamp-2 leading-relaxed">
            {issue.description}
          </p>
        )}

        {/* Footer row */}
        <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-700/50">
          <div className="flex items-center gap-3">
            {/* Votes */}
            <span className="flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500">
              <span>👍</span>
              <span>{issue.vote_count ?? 0}</span>
            </span>
            {/* Verifications */}
            <span className="flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500">
              <span>✓</span>
              <span>{issue.verification_count ?? 0} verified</span>
            </span>
          </div>

          <div className="flex items-center gap-2">
            {showDistance && dist && (
              <span className="text-[10px] text-primary-500 dark:text-primary-400 font-medium">
                📍 {formatDistance(dist)}
              </span>
            )}
            <span className="text-[10px] text-slate-400 dark:text-slate-500">
              {timeAgo(issue.created_at)}
            </span>
          </div>
        </div>
      </div>
    </button>
  );
}
