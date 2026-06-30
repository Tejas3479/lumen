import { useState, useEffect, useCallback } from 'react';
import { AlertTriangle, Download, CheckSquare, Square } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import api, { apiGet, apiPatch } from '@/lib/api';
import type { Issue, IssueStatus, PaginatedResponse } from '@/types';
import toast from 'react-hot-toast';
import { useUserStore } from '@/store/userStore';

interface TriageReport {
  recommended_department: string;
  recommended_priority: number;
  recommended_action: string;
  recommendation_summary: string;
  confidence: number;
}

const STATUS_OPTIONS: IssueStatus[] = [
  'reported', 'verified', 'assigned', 'in_progress', 'resolved', 'closed',
];

const STATUS_COLORS: Record<string, string> = {
  resolved:    'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  in_progress: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  disputed:    'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  verified:    'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  assigned:    'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  closed:      'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
  reported:    'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'text-red-600 dark:text-red-400',
  high:     'text-orange-600 dark:text-orange-400',
  medium:   'text-amber-600 dark:text-amber-400',
  low:      'text-slate-400 dark:text-slate-500',
};

interface Props {
  onIssueSelect: (issue: Issue) => void;
}

export default function AdminIssueQueue({ onIssueSelect }: Props) {
  const { token } = useUserStore();
  const [issues, setIssues] = useState<Issue[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkStatus, setBulkStatus] = useState<IssueStatus>('in_progress');
  const [filters, setFilters] = useState({
    status: '', category: '', ward: '', is_emergency: '',
  });
  const [triageReports, setTriageReports] = useState<Record<string, TriageReport>>({});

  const loadQueue = useCallback(async () => {
    setIsLoading(true);
    try {
      const params: Record<string, string> = { page: String(page), per_page: '25' };
      if (filters.status)       params.status       = filters.status;
      if (filters.category)     params.category     = filters.category;
      if (filters.ward)         params.ward         = filters.ward;
      if (filters.is_emergency) params.is_emergency = filters.is_emergency;

      const data = await apiGet<PaginatedResponse<Issue>>('/admin/queue', { params });
      setIssues(data.items);
      setTotal(data.total);
    } catch {
      toast.error('Failed to load admin queue');
    } finally {
      setIsLoading(false);
    }
  }, [page, filters]);

  useEffect(() => { loadQueue(); }, [loadQueue]);

  // Reset to page 1 on filter change
  useEffect(() => { setPage(1); }, [filters]);

  useEffect(() => {
    const loadTriage = async () => {
      const reports: Record<string, TriageReport> = {};
      await Promise.all(
        issues.map(async (issue) => {
          try {
            const triage = await apiGet<TriageReport>(`/ai/triage/${issue.id}`);
            if (triage && triage.recommended_action) {
              reports[issue.id] = triage;
            }
          } catch {
            // Triage pending or unavailable — skip
          }
        })
      );
      setTriageReports(reports);
    };
    if (issues.length > 0) loadTriage();
  }, [issues]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    selected.size === issues.length
      ? setSelected(new Set())
      : setSelected(new Set(issues.map((i) => i.id)));
  };

  const bulkUpdate = async () => {
    if (selected.size === 0) return;
    try {
      const result = await apiPatch<{ updated: string[]; errors: unknown[] }>('/admin/issues/bulk', {
        issue_ids: Array.from(selected),
        status: bulkStatus,
      });
      toast.success(`Updated ${result.updated?.length ?? 0} issues`);
      setSelected(new Set());
      loadQueue();
    } catch {
      toast.error('Bulk update failed');
    }
  };

  const exportCSV = async () => {
    try {
      const response = await fetch('/api/admin/export?format=csv', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Export failed');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'lumen_issues.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Export failed');
    }
  };

  const totalPages = Math.ceil(total / 25);

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Filters */}
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={filters.status}
            onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
            className="text-sm border border-slate-200 dark:border-slate-700 rounded-lg px-2 py-1.5
                       bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200"
            aria-label="Filter by status"
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{s.replace('_', ' ')}</option>
            ))}
          </select>

          <select
            value={filters.is_emergency}
            onChange={(e) => setFilters((f) => ({ ...f, is_emergency: e.target.value }))}
            className="text-sm border border-slate-200 dark:border-slate-700 rounded-lg px-2 py-1.5
                       bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200"
            aria-label="Filter by priority"
          >
            <option value="">All priority</option>
            <option value="true">🚨 Emergency only</option>
          </select>

          <input
            type="text"
            placeholder="Ward…"
            value={filters.ward}
            onChange={(e) => setFilters((f) => ({ ...f, ward: e.target.value }))}
            className="text-sm border border-slate-200 dark:border-slate-700 rounded-lg px-2 py-1.5 w-28
                       bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200
                       placeholder:text-slate-400"
            aria-label="Filter by ward"
          />
        </div>

        {/* Bulk actions — shown when items selected */}
        {selected.size > 0 && (
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-sm text-slate-600 dark:text-slate-400">
              {selected.size} selected
            </span>
            <select
              value={bulkStatus}
              onChange={(e) => setBulkStatus(e.target.value as IssueStatus)}
              className="text-sm border border-slate-200 dark:border-slate-700 rounded-lg px-2 py-1.5
                         bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200"
              aria-label="Bulk action status"
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>{s.replace('_', ' ')}</option>
              ))}
            </select>
            <button
              onClick={bulkUpdate}
              className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-1.5 rounded-lg
                         transition-colors font-medium"
              aria-label={`Update ${selected.size} issues to ${bulkStatus}`}
            >
              Update {selected.size}
            </button>
          </div>
        )}

        {/* Export */}
        <button
          onClick={exportCSV}
          className="ml-auto flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-400
                     border border-slate-200 dark:border-slate-700 px-3 py-1.5 rounded-lg
                     hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          aria-label="Export issues as CSV"
        >
          <Download size={14} aria-hidden="true" />
          Export CSV
        </button>
      </div>

      {/* Count */}
      <p className="text-sm text-slate-500 dark:text-slate-400">
        {total} issue{total !== 1 ? 's' : ''} in queue
      </p>

      {/* Table */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
        {/* Column headers */}
        <div className="flex items-center gap-3 px-4 py-2.5 bg-slate-50 dark:bg-slate-800/50
                        border-b border-slate-200 dark:border-slate-800
                        text-xs font-medium text-slate-500 dark:text-slate-400">
          <button
            onClick={selectAll}
            className="flex-shrink-0"
            aria-label={selected.size === issues.length ? 'Deselect all' : 'Select all'}
          >
            {selected.size === issues.length && issues.length > 0
              ? <CheckSquare size={16} className="text-blue-600" aria-hidden="true" />
              : <Square size={16} aria-hidden="true" />
            }
          </button>
          <span className="flex-1">Issue</span>
          <span className="w-24 text-center hidden sm:block">Status</span>
          <span className="w-20 hidden sm:block">Severity</span>
          <span className="w-28 hidden md:block">Reported</span>
        </div>

        {/* Skeleton */}
        {isLoading ? (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-[60px] px-4 py-3 flex items-center gap-3" aria-hidden="true">
                <div className="w-4 h-4 bg-slate-200 dark:bg-slate-700 rounded animate-pulse" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3.5 bg-slate-200 dark:bg-slate-700 rounded animate-pulse w-3/4" />
                  <div className="h-2.5 bg-slate-100 dark:bg-slate-800 rounded animate-pulse w-1/2" />
                </div>
              </div>
            ))}
          </div>
        ) : issues.length === 0 ? (
          <div className="text-center py-16 text-slate-400 dark:text-slate-500 text-sm">
            No issues match the current filters
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {issues.map((issue) => (
              <div
                key={issue.id}
                className={[
                  'flex items-center gap-3 px-4 py-3',
                  'hover:bg-slate-50 dark:hover:bg-slate-800/40 cursor-pointer transition-colors',
                  issue.is_emergency
                    ? 'border-l-4 border-l-red-500'
                    : 'border-l-4 border-l-transparent',
                  selected.has(issue.id)
                    ? 'bg-blue-50 dark:bg-blue-950/30'
                    : '',
                ].join(' ')}
                onClick={() => onIssueSelect(issue)}
              >
                {/* Checkbox */}
                <button
                  onClick={(e) => { e.stopPropagation(); toggleSelect(issue.id); }}
                  className="flex-shrink-0"
                  aria-label={`${selected.has(issue.id) ? 'Deselect' : 'Select'} issue: ${issue.title}`}
                >
                  {selected.has(issue.id)
                    ? <CheckSquare size={16} className="text-blue-600" aria-hidden="true" />
                    : <Square size={16} className="text-slate-300 dark:text-slate-600" aria-hidden="true" />
                  }
                </button>

                {/* Issue info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {issue.is_emergency && (
                      <AlertTriangle
                        size={12}
                        className="text-red-500 flex-shrink-0 animate-pulse"
                        aria-label="Emergency"
                      />
                    )}
                    <span className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
                      {issue.title}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 dark:text-slate-500 mt-0.5 truncate">
                    {issue.ward || 'No ward'} · {issue.vote_count} vote{issue.vote_count !== 1 ? 's' : ''}
                    {' '}· {issue.verification_count} verified
                  </div>
                  {triageReports[issue.id] && (
                    <details className="mt-1">
                      <summary
                        className="flex items-center gap-1.5 cursor-pointer list-none"
                        aria-label={`AI triage: ${triageReports[issue.id].recommended_action.replace('_', ' ')} — click to see reasoning`}
                      >
                        <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-semibold">
                          🤖 {triageReports[issue.id].recommended_department}
                        </span>
                        <span className={`text-xs font-bold ${
                          triageReports[issue.id].recommended_priority <= 2 ? 'text-red-600' :
                          triageReports[issue.id].recommended_priority <= 4 ? 'text-orange-500' :
                          'text-gray-400'
                        }`}>
                          P{triageReports[issue.id].recommended_priority}
                        </span>
                        <span className="text-xs text-gray-400">
                          {triageReports[issue.id].recommended_action.replace(/_/g, ' ')}
                        </span>
                      </summary>
                      <div className="mt-1.5 ml-1 text-xs text-gray-600 bg-purple-50 rounded-lg px-3 py-2 border-l-2 border-purple-300">
                        <span className="font-medium text-purple-700">AI reasoning: </span>
                        {triageReports[issue.id].recommendation_summary}
                      </div>
                    </details>
                  )}
                </div>

                {/* Status badge */}
                <span className="w-24 hidden sm:flex justify-center">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    STATUS_COLORS[issue.status] ?? STATUS_COLORS.reported
                  }`}>
                    {issue.status.replace('_', ' ')}
                  </span>
                </span>

                {/* Severity */}
                <span className={`w-20 hidden sm:block text-xs font-semibold ${
                  SEVERITY_COLORS[issue.severity] ?? SEVERITY_COLORS.low
                }`}>
                  {issue.severity}
                </span>

                {/* Age */}
                <span className="w-28 hidden md:block text-xs text-slate-400 dark:text-slate-500">
                  {formatDistanceToNow(new Date(issue.created_at), { addSuffix: true })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg
                       disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            aria-label="Previous page"
          >
            ← Prev
          </button>
          <span className="text-slate-500 dark:text-slate-400">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg
                       disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            aria-label="Next page"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
