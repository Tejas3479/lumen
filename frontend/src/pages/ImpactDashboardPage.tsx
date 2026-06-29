import { useEffect, useState } from 'react';
import {
  TrendingUp, CheckCircle, Clock, Trophy, Map,
  BarChart3, Flame,
} from 'lucide-react';
import { apiGet } from '@/lib/api';
import type { DashboardStats } from '@/types';
import MobileBottomNav from '@/components/MobileBottomNav';

// ── Mini bar chart for category/status breakdowns ─────────────────
function BarList({ data, colorClass = 'bg-blue-500' }: {
  data: [string, number][];
  colorClass?: string;
}) {
  const max = Math.max(...data.map(([, v]) => v), 1);
  return (
    <ul className="space-y-2.5" role="list">
      {data.map(([label, count]) => (
        <li key={label} className="space-y-1">
          <div className="flex justify-between text-xs text-slate-600 dark:text-slate-400">
            <span className="capitalize">{label.replace('_', ' ')}</span>
            <span className="font-semibold text-slate-800 dark:text-slate-200">{count}</span>
          </div>
          <div className="h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${colorClass}`}
              style={{ width: `${Math.max(3, (count / max) * 100)}%` }}
              role="progressbar"
              aria-valuenow={count}
              aria-valuemax={max}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

// ── Stat card ─────────────────────────────────────────────────────
function StatCard({
  label, value, icon: Icon, color, bg,
}: {
  label: string;
  value: string | number;
  icon: typeof TrendingUp;
  color: string;
  bg: string;
}) {
  return (
    <div className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-100 dark:border-slate-800
                    shadow-sm flex items-start gap-3">
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${bg}`}>
        <Icon size={18} className={color} aria-hidden="true" />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 leading-none">
          {value}
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 leading-tight">
          {label}
        </p>
      </div>
    </div>
  );
}

// ── Skeleton loader ───────────────────────────────────────────────
function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`bg-slate-200 dark:bg-slate-800 rounded-xl animate-pulse ${className}`}
      aria-hidden="true"
    />
  );
}

export default function ImpactDashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [wardReport, setWardReport] = useState<{
    ward: string;
    headline: string;
    narrative: string;
    key_achievements: string[];
    key_concerns: string[];
    generated_at: string;
  } | null>(null);

  useEffect(() => {
    apiGet<DashboardStats>('/analytics/dashboard')
      .then(setStats)
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    if (stats?.top_wards?.[0]?.ward) {
      const topWard = stats.top_wards[0].ward;
      apiGet<any>(`/analytics/ward-report/${encodeURIComponent(topWard)}`)
        .then(setWardReport)
        .catch(() => {});
    }
  }, [stats?.top_wards?.[0]?.ward]);

  const statCards = stats
    ? [
        {
          label: 'Total Issues Reported',
          value: stats.total_issues.toLocaleString(),
          icon: TrendingUp,
          color: 'text-blue-600 dark:text-blue-400',
          bg: 'bg-blue-50 dark:bg-blue-900/30',
        },
        {
          label: 'Resolved This Month',
          value: stats.resolved_this_month.toLocaleString(),
          icon: CheckCircle,
          color: 'text-emerald-600 dark:text-emerald-400',
          bg: 'bg-emerald-50 dark:bg-emerald-900/30',
        },
        {
          label: 'Resolution Rate',
          value: `${stats.resolution_rate}%`,
          icon: Trophy,
          color: 'text-amber-600 dark:text-amber-400',
          bg: 'bg-amber-50 dark:bg-amber-900/30',
        },
        {
          label: 'Avg. Days to Resolve',
          value: stats.avg_resolution_days > 0 ? `${stats.avg_resolution_days}d` : 'N/A',
          icon: Clock,
          color: 'text-purple-600 dark:text-purple-400',
          bg: 'bg-purple-50 dark:bg-purple-900/30',
        },
      ]
    : [];

  return (
    <main className="min-h-screen bg-slate-50 dark:bg-slate-950 pb-24">
      {/* Header */}
      <header className="bg-white dark:bg-slate-900 px-4 py-5 border-b border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-blue-50 dark:bg-blue-900/30 rounded-xl flex items-center justify-center">
            <BarChart3 size={18} className="text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              Community Impact
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              See how your reports make a difference
            </p>
          </div>
        </div>
      </header>

      <div className="px-4 py-5 space-y-6 max-w-2xl mx-auto">
        {/* Stat cards */}
        {isLoading ? (
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        ) : stats ? (
          <div className="grid grid-cols-2 gap-3">
            {statCards.map((card) => (
              <StatCard key={card.label} {...card} />
            ))}
          </div>
        ) : (
          <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-100 dark:border-slate-800
                          text-center text-sm text-slate-400 dark:text-slate-500">
            Could not load impact data
          </div>
        )}

        {/* Issues by category */}
        {isLoading ? (
          <Skeleton className="h-48" />
        ) : stats && Object.keys(stats.issues_by_category).length > 0 ? (
          <section
            className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-100 dark:border-slate-800 shadow-sm"
            aria-labelledby="category-heading"
          >
            <div className="flex items-center gap-2 mb-4">
              <Flame size={16} className="text-orange-500" aria-hidden="true" />
              <h2 id="category-heading" className="text-sm font-bold text-slate-800 dark:text-slate-200">
                Issues by Category
              </h2>
            </div>
            <BarList
              data={Object.entries(stats.issues_by_category)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 7)}
              colorClass="bg-orange-400"
            />
          </section>
        ) : null}

        {/* Issues by status */}
        {isLoading ? (
          <Skeleton className="h-40" />
        ) : stats && Object.keys(stats.issues_by_status).length > 0 ? (
          <section
            className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-100 dark:border-slate-800 shadow-sm"
            aria-labelledby="status-heading"
          >
            <div className="flex items-center gap-2 mb-4">
              <CheckCircle size={16} className="text-emerald-500" aria-hidden="true" />
              <h2 id="status-heading" className="text-sm font-bold text-slate-800 dark:text-slate-200">
                Issues by Status
              </h2>
            </div>
            <BarList
              data={Object.entries(stats.issues_by_status).sort(([, a], [, b]) => b - a)}
              colorClass="bg-emerald-400"
            />
          </section>
        ) : null}

        {/* Top wards */}
        {isLoading ? (
          <Skeleton className="h-36" />
        ) : stats && stats.top_wards.length > 0 ? (
          <section
            className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-100 dark:border-slate-800 shadow-sm"
            aria-labelledby="wards-heading"
          >
            <div className="flex items-center gap-2 mb-4">
              <Map size={16} className="text-blue-500" aria-hidden="true" />
              <h2 id="wards-heading" className="text-sm font-bold text-slate-800 dark:text-slate-200">
                Top Wards by Issues
              </h2>
            </div>
            <div className="space-y-2" role="list">
              {stats.top_wards.map((ward, idx) => (
                <div
                  key={ward.ward}
                  className="flex items-center gap-3"
                  role="listitem"
                >
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold
                    ${idx === 0 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' :
                      idx === 1 ? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300' :
                      idx === 2 ? 'bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-400' :
                      'bg-slate-50 text-slate-500 dark:bg-slate-900 dark:text-slate-500'}`}
                  >
                    {idx + 1}
                  </span>
                  <span className="flex-1 text-sm text-slate-700 dark:text-slate-300 font-medium">
                    {ward.ward}
                  </span>
                  <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {ward.count}
                  </span>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {/* Weekly Ward Report */}
        {wardReport && (
          <section
            className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-100 dark:border-slate-800 shadow-sm space-y-4"
            aria-labelledby="ward-report-heading"
          >
            <div className="flex items-center gap-2">
              <span className="text-lg">📰</span>
              <h2 id="ward-report-heading" className="text-sm font-bold text-slate-800 dark:text-slate-200">
                {wardReport.ward} — Weekly Report
              </h2>
            </div>
            <div className="space-y-3">
              <p className="text-sm font-bold text-slate-900 dark:text-slate-100 leading-tight">
                {wardReport.headline}
              </p>
              <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed whitespace-pre-line">
                {wardReport.narrative}
              </p>

              {wardReport.key_achievements && wardReport.key_achievements.length > 0 && (
                <div className="pt-2">
                  <div className="text-xs font-bold text-emerald-600 dark:text-emerald-400 mb-1 flex items-center gap-1">
                    <span>✓</span> This week's wins
                  </div>
                  <ul className="space-y-1 list-disc pl-4" role="list">
                    {wardReport.key_achievements.map((a, i) => (
                      <li key={i} className="text-xs text-slate-600 dark:text-slate-400 leading-tight">
                        {a}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {wardReport.key_concerns && wardReport.key_concerns.length > 0 && (
                <div className="pt-2">
                  <div className="text-xs font-bold text-amber-600 dark:text-amber-400 mb-1 flex items-center gap-1">
                    <span>⚠</span> Still needs attention
                  </div>
                  <ul className="space-y-1 list-disc pl-4" role="list">
                    {wardReport.key_concerns.map((c, i) => (
                      <li key={i} className="text-xs text-slate-600 dark:text-slate-400 leading-tight">
                        {c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex justify-between items-center text-[10px] text-slate-400 dark:text-slate-500">
                <span>Generated by Lumen AI</span>
                <span>{new Date(wardReport.generated_at).toLocaleDateString()}</span>
              </div>
            </div>
          </section>
        )}
      </div>

      <MobileBottomNav />
    </main>
  );
}
