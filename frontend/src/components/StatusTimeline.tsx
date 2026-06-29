/**
 * StatusTimeline — vertical accessible status history timeline.
 * Renders each status transition with icon, label, actor, and timestamp.
 * The latest entry receives a subtle ring highlight.
 */
import { formatDistanceToNow, format } from 'date-fns';
import { CheckCircle, Circle, Clock, AlertTriangle, Shield } from 'lucide-react';
import type { StatusHistoryEntry, IssueStatus } from '@/types';

// ── Status appearance config ────────────────────────────────────
const STATUS_CONFIG: Record<
  IssueStatus,
  {
    label: string;
    color: string;
    bgColor: string;
    borderColor: string;
    Icon: React.ElementType;
  }
> = {
  reported: {
    label: 'Issue Reported',
    color: 'text-gray-600',
    bgColor: 'bg-gray-100',
    borderColor: 'border-gray-300',
    Icon: Circle,
  },
  verified: {
    label: 'Community Verified',
    color: 'text-blue-700',
    bgColor: 'bg-blue-100',
    borderColor: 'border-blue-400',
    Icon: CheckCircle,
  },
  assigned: {
    label: 'Assigned to Team',
    color: 'text-purple-700',
    bgColor: 'bg-purple-100',
    borderColor: 'border-purple-400',
    Icon: Shield,
  },
  in_progress: {
    label: 'Work in Progress',
    color: 'text-amber-700',
    bgColor: 'bg-amber-100',
    borderColor: 'border-amber-400',
    Icon: Clock,
  },
  resolved: {
    label: 'Marked Resolved',
    color: 'text-green-700',
    bgColor: 'bg-green-100',
    borderColor: 'border-green-500',
    Icon: CheckCircle,
  },
  disputed: {
    label: 'Resolution Disputed',
    color: 'text-red-700',
    bgColor: 'bg-red-100',
    borderColor: 'border-red-500',
    Icon: AlertTriangle,
  },
  closed: {
    label: 'Closed',
    color: 'text-gray-500',
    bgColor: 'bg-gray-100',
    borderColor: 'border-gray-300',
    Icon: Circle,
  },
};

// Fallback for any unexpected status values
const FALLBACK_CONFIG = STATUS_CONFIG['reported'];

// ── Component ───────────────────────────────────────────────────
interface Props {
  history: StatusHistoryEntry[];
  currentStatus: IssueStatus;
}

export default function StatusTimeline({ history, currentStatus: _currentStatus }: Props) {
  if (!history || history.length === 0) {
    return (
      <div className="text-sm text-gray-400 py-4 text-center">
        No status history available
      </div>
    );
  }

  return (
    <div
      className="relative"
      role="list"
      aria-label="Issue status history"
    >
      {/* Vertical connector line — sits behind the icon dots */}
      <div
        className="absolute left-[18px] top-5 bottom-5 w-0.5 bg-gray-200"
        aria-hidden="true"
      />

      <div className="space-y-4">
        {history.map((entry, index) => {
          const config =
            STATUS_CONFIG[entry.to_status as IssueStatus] ?? FALLBACK_CONFIG;
          const { Icon } = config;
          const isLatest = index === history.length - 1;
          const timeAgo = formatDistanceToNow(new Date(entry.changed_at), {
            addSuffix: true,
          });
          const fullDate = format(
            new Date(entry.changed_at),
            'dd MMM yyyy, h:mm a'
          );

          return (
            <div
              key={entry.id}
              className="flex gap-4"
              role="listitem"
              aria-label={`${config.label} — ${timeAgo}`}
            >
              {/* Status icon dot */}
              <div className="flex-shrink-0 relative z-10">
                <div
                  className={[
                    'w-9 h-9 rounded-full border-2 flex items-center justify-center',
                    config.bgColor,
                    config.borderColor,
                    isLatest ? 'ring-2 ring-offset-2 ring-blue-300' : '',
                  ].join(' ')}
                  aria-hidden="true"
                >
                  <Icon size={16} className={config.color} />
                </div>
              </div>

              {/* Content block */}
              <div className="flex-1 pb-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    {/* Status label + official badge */}
                    <div className={`text-sm font-semibold ${config.color}`}>
                      {config.label}
                      {entry.is_official && (
                        <span
                          className="ml-2 text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium"
                          aria-label="Official update"
                        >
                          Official
                        </span>
                      )}
                    </div>

                    {/* Actor attribution */}
                    <div className="text-xs text-gray-400 mt-0.5">
                      {entry.changed_by_user
                        ? entry.is_official
                          ? `${entry.changed_by_user.department ?? 'Official'} · ${entry.changed_by_user.display_name}`
                          : (entry.changed_by_user.pseudonym ??
                            entry.changed_by_user.display_name)
                        : 'System'}
                    </div>
                  </div>

                  {/* Relative timestamp with full date as tooltip */}
                  <time
                    dateTime={entry.changed_at}
                    title={fullDate}
                    className="text-xs text-gray-400 flex-shrink-0"
                  >
                    {timeAgo}
                  </time>
                </div>

                {/* Optional note — skip default system notes */}
                {entry.note &&
                  entry.note !== `Status changed to ${entry.to_status}` && (
                    <div
                      className={[
                        'mt-2 text-xs px-3 py-2 rounded-lg',
                        entry.is_official
                          ? 'bg-blue-50 text-blue-800 border border-blue-100'
                          : 'bg-gray-50 text-gray-600',
                      ].join(' ')}
                    >
                      {entry.note}
                    </div>
                  )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
