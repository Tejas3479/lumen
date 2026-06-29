import { Trophy, Star, Flame } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface LeaderboardEntry {
  rank: number;
  user_id: string;
  display_name: string;
  pseudonym: string | null;
  points: number;
  level: number;
  badge_count: number;
  issues_resolved_count: number;
  streak_days: number;
}

interface Props {
  entries: LeaderboardEntry[];
  currentUserId?: string;
  isLoading?: boolean;
}

const RANK_STYLES: Record<number, { bg: string; text: string; icon?: string }> = {
  1: { bg: 'bg-amber-100 dark:bg-amber-900/40', text: 'text-amber-700 dark:text-amber-300', icon: '🥇' },
  2: { bg: 'bg-slate-100 dark:bg-slate-800', text: 'text-slate-600 dark:text-slate-300', icon: '🥈' },
  3: { bg: 'bg-orange-50 dark:bg-orange-900/30', text: 'text-orange-700 dark:text-orange-400', icon: '🥉' },
};

function RankBadge({ rank }: { rank: number }) {
  const style = RANK_STYLES[rank];
  if (style) {
    return (
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0 ${style.bg}`}
        aria-label={`Rank ${rank}`}
      >
        {style.icon}
      </div>
    );
  }
  return (
    <div
      className="w-8 h-8 rounded-full bg-slate-50 dark:bg-slate-800 flex items-center justify-center
                  text-xs font-bold text-slate-500 dark:text-slate-400 flex-shrink-0"
      aria-label={`Rank ${rank}`}
    >
      {rank}
    </div>
  );
}

export default function LeaderboardTable({
  entries,
  currentUserId,
  isLoading = false,
}: Props) {
  const navigate = useNavigate();

  if (isLoading) {
    return (
      <div className="space-y-2" aria-busy="true">
        {Array.from({ length: 10 }).map((_, i) => (
          <div
            key={i}
            className="h-16 bg-slate-100 dark:bg-slate-800 rounded-2xl animate-pulse"
            aria-hidden="true"
          />
        ))}
        <span className="sr-only" role="status">Loading leaderboard…</span>
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-2xl p-8 border border-slate-100 dark:border-slate-800
                      text-center">
        <Trophy size={32} className="text-slate-200 dark:text-slate-700 mx-auto mb-3" />
        <p className="text-sm text-slate-400 dark:text-slate-500">
          No leaderboard data available yet.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2" role="list" aria-label="Leaderboard">
      {entries.map((entry) => {
        const isMe = entry.user_id === currentUserId;
        const name = entry.pseudonym || entry.display_name;

        return (
          <article
            key={entry.user_id}
            role="listitem"
            onClick={() => navigate(`/profile/${entry.user_id}`)}
            className={[
              'bg-white dark:bg-slate-900 rounded-2xl px-4 py-3',
              'border cursor-pointer transition-all',
              'hover:shadow-md hover:-translate-y-0.5',
              isMe
                ? 'border-blue-300 dark:border-blue-700 ring-1 ring-blue-300 dark:ring-blue-700'
                : 'border-slate-100 dark:border-slate-800 shadow-sm',
            ].join(' ')}
            aria-label={`${name}, rank ${entry.rank}, ${entry.points.toLocaleString()} points`}
          >
            <div className="flex items-center gap-3">
              <RankBadge rank={entry.rank} />

              {/* Name + level */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-semibold truncate ${
                    isMe
                      ? 'text-blue-700 dark:text-blue-300'
                      : 'text-slate-800 dark:text-slate-200'
                  }`}>
                    {name}
                    {isMe && (
                      <span className="ml-1.5 text-xs text-blue-500 dark:text-blue-400">(you)</span>
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                  <span className="text-xs text-slate-400 dark:text-slate-500">
                    Lv {entry.level}
                  </span>
                  {entry.badge_count > 0 && (
                    <span className="flex items-center gap-0.5 text-xs text-amber-600 dark:text-amber-400">
                      <Star size={9} aria-hidden="true" />
                      {entry.badge_count} badge{entry.badge_count !== 1 ? 's' : ''}
                    </span>
                  )}
                  {entry.streak_days >= 3 && (
                    <span className="flex items-center gap-0.5 text-xs text-orange-500">
                      <Flame size={9} aria-hidden="true" />
                      {entry.streak_days}d
                    </span>
                  )}
                  {entry.issues_resolved_count > 0 && (
                    <span className="text-xs text-emerald-600 dark:text-emerald-400">
                      ✓ {entry.issues_resolved_count} resolved
                    </span>
                  )}
                </div>
              </div>

              {/* Points */}
              <div className="text-right flex-shrink-0">
                <p className="text-base font-bold text-slate-900 dark:text-slate-100">
                  {entry.points.toLocaleString()}
                </p>
                <p className="text-xs text-slate-400 dark:text-slate-500">pts</p>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
