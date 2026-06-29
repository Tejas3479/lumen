import { useEffect, useState } from 'react';
import { TrendingUp, AlertTriangle, MapPin, Calendar, Zap } from 'lucide-react';
import { apiGet } from '@/lib/api';
import type { PredictiveHotspot } from '@/types';

const CONFIDENCE_LABEL: Record<string, { text: string; color: string }> = {
  high:   { text: 'High', color: 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30' },
  medium: { text: 'Med',  color: 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/30' },
  low:    { text: 'Low',  color: 'text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800' },
};

function getConfidenceLevel(confidence: number): string {
  if (confidence >= 0.7) return 'high';
  if (confidence >= 0.4) return 'medium';
  return 'low';
}

interface Props {
  category?: string;
  ward?: string;
}

export default function PredictiveInsightsPanel({ category, ward }: Props) {
  const [hotspots, setHotspots] = useState<PredictiveHotspot[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const params: Record<string, string> = {};
    if (category) params.category = category;

    apiGet<PredictiveHotspot[]>('/analytics/hotspots', category ? { params: { category } } : undefined)
      .then((data) => {
        // If ward filter set, filter client-side
        const filtered = ward
          ? data.filter((h) => h.ward?.toLowerCase().includes(ward.toLowerCase()))
          : data;
        setHotspots(filtered);
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [category, ward]);

  if (isLoading) {
    return (
      <div className="space-y-3" aria-busy="true">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="h-20 bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse"
            aria-hidden="true"
          />
        ))}
        <span className="sr-only" role="status">Loading hotspot predictions…</span>
      </div>
    );
  }

  if (hotspots.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-100 dark:border-slate-800
                      text-center">
        <TrendingUp size={28} className="text-slate-300 dark:text-slate-600 mx-auto mb-3" />
        <p className="text-sm text-slate-500 dark:text-slate-400">
          No hotspot predictions available yet.
          <br />
          <span className="text-xs">More data needed to identify patterns.</span>
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3" role="list" aria-label="Predicted hotspots">
      {hotspots.map((hotspot, idx) => {
        const level = getConfidenceLevel(hotspot.confidence);
        const badge = CONFIDENCE_LABEL[level];
        const pct = Math.round(hotspot.confidence * 100);

        return (
          <article
            key={hotspot.id}
            className="bg-white dark:bg-slate-900 rounded-2xl p-4
                       border border-slate-100 dark:border-slate-800 shadow-sm"
            role="listitem"
          >
            <div className="flex items-start gap-3">
              {/* Rank */}
              <div className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0
                ${idx === 0 ? 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400' :
                  idx === 1 ? 'bg-orange-100 text-orange-600 dark:bg-orange-900/30 dark:text-orange-400' :
                  'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}`}
              >
                {idx + 1}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 capitalize">
                    {hotspot.category.replace(/_/g, ' ')}
                  </h3>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${badge.color}`}>
                    {badge.text} ({pct}%)
                  </span>
                  {hotspot.issue_count >= 10 && (
                    <span className="flex items-center gap-0.5 text-xs text-red-500 font-medium">
                      <Zap size={10} aria-hidden="true" />
                      Surge
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                  <span className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                    <AlertTriangle size={11} aria-hidden="true" />
                    {hotspot.issue_count} issues
                  </span>

                  {hotspot.ward && (
                    <span className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                      <MapPin size={11} aria-hidden="true" />
                      {hotspot.ward}
                    </span>
                  )}

                  {hotspot.predicted_next_issue_date && (
                    <span className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                      <Calendar size={11} aria-hidden="true" />
                      Next: {new Date(hotspot.predicted_next_issue_date).toLocaleDateString('en-US', {
                        month: 'short', day: 'numeric',
                      })}
                    </span>
                  )}
                </div>

                {/* Confidence bar */}
                <div className="mt-2 h-1 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${
                      level === 'high' ? 'bg-red-500' :
                      level === 'medium' ? 'bg-amber-500' :
                      'bg-slate-400'
                    }`}
                    style={{ width: `${pct}%` }}
                    role="progressbar"
                    aria-valuenow={pct}
                    aria-valuemax={100}
                    aria-label={`Confidence: ${pct}%`}
                  />
                </div>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
