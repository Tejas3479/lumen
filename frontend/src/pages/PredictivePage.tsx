import { useState } from 'react';
import { Zap, Map, TrendingUp, Filter } from 'lucide-react';
import HotspotHeatmap from '@/components/HotspotHeatmap';
import PredictiveInsightsPanel from '@/components/PredictiveInsightsPanel';
import MobileBottomNav from '@/components/MobileBottomNav';

type View = 'map' | 'insights';

export default function PredictivePage() {
  const [view, setView] = useState<View>('insights');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [wardFilter, setWardFilter] = useState('');

  return (
    <main className="min-h-screen bg-slate-50 dark:bg-slate-950 pb-24">
      {/* Header */}
      <header className="bg-white dark:bg-slate-900 px-4 py-5 border-b border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-purple-50 dark:bg-purple-900/30 rounded-xl flex items-center justify-center">
            <Zap size={18} className="text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              Predictive Hotspots
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              AI-identified areas at risk of civic issues
            </p>
          </div>
        </div>
      </header>

      {/* View toggle + filters */}
      <div className="bg-white dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800 px-4 py-3">
        <div className="flex items-center gap-3 flex-wrap">
          {/* Map / Insights toggle */}
          <div className="flex bg-slate-100 dark:bg-slate-800 rounded-xl p-1" role="group" aria-label="View toggle">
            {(['insights', 'map'] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={[
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
                  view === v
                    ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300',
                ].join(' ')}
                aria-pressed={view === v}
              >
                {v === 'insights'
                  ? <><TrendingUp size={12} aria-hidden="true" /> Insights</>
                  : <><Map size={12} aria-hidden="true" /> Map</>
                }
              </button>
            ))}
          </div>

          {/* Filters */}
          <div className="flex items-center gap-2 ml-auto">
            <Filter size={13} className="text-slate-400" aria-hidden="true" />
            <input
              type="text"
              placeholder="Category…"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="text-xs border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 w-28
                         bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200
                         placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              aria-label="Filter by category"
            />
            <input
              type="text"
              placeholder="Ward…"
              value={wardFilter}
              onChange={(e) => setWardFilter(e.target.value)}
              className="text-xs border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 w-24
                         bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200
                         placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              aria-label="Filter by ward"
            />
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-4 py-5 max-w-2xl mx-auto">
        {/* Info banner */}
        <div className="mb-5 bg-purple-50 dark:bg-purple-900/20 border border-purple-100 dark:border-purple-800/50
                        rounded-2xl px-4 py-3 flex items-start gap-3">
          <Zap size={16} className="text-purple-500 mt-0.5 flex-shrink-0" aria-hidden="true" />
          <p className="text-xs text-purple-700 dark:text-purple-300 leading-relaxed">
            Hotspots are predicted using geographic clustering of the last 90 days of civic reports.
            Confidence reflects cluster density and recency.
          </p>
        </div>

        {view === 'map' ? (
          <HotspotHeatmap
            category={categoryFilter || undefined}
            ward={wardFilter || undefined}
            height="450px"
          />
        ) : (
          <PredictiveInsightsPanel
            category={categoryFilter || undefined}
            ward={wardFilter || undefined}
          />
        )}
      </div>

      <MobileBottomNav />
    </main>
  );
}
