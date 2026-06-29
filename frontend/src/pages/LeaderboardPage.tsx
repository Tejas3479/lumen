import { useEffect, useState, useCallback } from 'react';
import { Trophy, ChevronLeft, ChevronRight } from 'lucide-react';
import { apiGet } from '@/lib/api';
import LeaderboardTable from '@/components/LeaderboardTable';
import MobileBottomNav from '@/components/MobileBottomNav';
import { useUserStore } from '@/store/userStore';

type Period = 'all_time' | 'monthly' | 'weekly';

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

interface LeaderboardResponse {
  items: LeaderboardEntry[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
  period: string;
}

const PERIODS: { id: Period; label: string }[] = [
  { id: 'all_time', label: 'All Time' },
  { id: 'monthly',  label: 'This Month' },
  { id: 'weekly',   label: 'This Week' },
];

export default function LeaderboardPage() {
  const { user } = useUserStore();
  const [period, setPeriod] = useState<Period>('all_time');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<LeaderboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchLeaderboard = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await apiGet<LeaderboardResponse>('/gamification/leaderboard', {
        params: { period, page: String(page), per_page: '25' },
      });
      setData(response);
    } catch {
      // Silently fail — table shows empty state
    } finally {
      setIsLoading(false);
    }
  }, [period, page]);

  useEffect(() => { fetchLeaderboard(); }, [fetchLeaderboard]);

  // Reset page when period changes
  useEffect(() => { setPage(1); }, [period]);

  const totalPages = data?.pages ?? 1;

  return (
    <main className="min-h-screen bg-slate-50 dark:bg-slate-950 pb-24">
      {/* Header */}
      <header className="bg-white dark:bg-slate-900 px-4 py-5 border-b border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-amber-50 dark:bg-amber-900/30 rounded-xl flex items-center justify-center">
            <Trophy size={18} className="text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              Leaderboard
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Top civic heroes in your community
            </p>
          </div>
        </div>
      </header>

      {/* Period selector */}
      <div className="bg-white dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800 px-4 py-3">
        <div
          className="flex bg-slate-100 dark:bg-slate-800 rounded-xl p-1 gap-1"
          role="group"
          aria-label="Time period filter"
        >
          {PERIODS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setPeriod(id)}
              className={[
                'flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all',
                period === id
                  ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300',
              ].join(' ')}
              aria-pressed={period === id}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="px-4 py-5 max-w-2xl mx-auto space-y-4">
        {/* Current user's rank hint */}
        {user && !user.is_guest && (
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800/50
                          rounded-2xl px-4 py-3 flex items-center gap-3">
            <Trophy size={16} className="text-blue-500 flex-shrink-0" aria-hidden="true" />
            <div>
              <p className="text-xs text-blue-700 dark:text-blue-300 font-medium">
                Your total: {user.points.toLocaleString()} pts · Level {user.level}
              </p>
              <p className="text-xs text-blue-500 dark:text-blue-400">
                Keep reporting and verifying to climb the rankings!
              </p>
            </div>
          </div>
        )}

        {/* Leaderboard table */}
        <LeaderboardTable
          entries={data?.items ?? []}
          currentUserId={user?.id}
          isLoading={isLoading}
        />

        {/* Pagination */}
        {!isLoading && totalPages > 1 && (
          <div className="flex items-center justify-center gap-3 text-sm">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="w-9 h-9 flex items-center justify-center border border-slate-200 dark:border-slate-700
                         rounded-xl disabled:opacity-40 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              aria-label="Previous page"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-slate-500 dark:text-slate-400 text-xs font-medium">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="w-9 h-9 flex items-center justify-center border border-slate-200 dark:border-slate-700
                         rounded-xl disabled:opacity-40 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              aria-label="Next page"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>

      <MobileBottomNav />
    </main>
  );
}
