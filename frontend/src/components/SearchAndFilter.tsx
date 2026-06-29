/**
 * SearchAndFilter — floating search bar + collapsible filter panel.
 *
 * Features:
 *  - Text search input with clear button
 *  - Category dropdown (matches backend Category.name slugs)
 *  - Status dropdown
 *  - Severity dropdown
 *  - Emergency-only toggle
 *  - "Apply" button triggers GET /issues with query params
 *  - "Clear" button resets all filters and reloads default issue list
 *  - Active filter indicator on the filter toggle button
 *
 * State is local — search params are not persisted to the URL (Session 21).
 */
import { useState, useCallback } from 'react';
import { Search, SlidersHorizontal, X } from 'lucide-react';
import { useIssueStore } from '@/store/issueStore';
import { apiGet } from '@/lib/api';
import type { PaginatedResponse, Issue } from '@/types';

// ── Options ──────────────────────────────────────────────────
const CATEGORY_OPTIONS = [
  { value: '',              label: 'All categories'  },
  { value: 'pothole',       label: '🕳️ Pothole'       },
  { value: 'water_leakage', label: '💧 Water Leakage' },
  { value: 'streetlight',   label: '💡 Streetlight'   },
  { value: 'garbage',       label: '🗑️ Garbage'       },
  { value: 'drainage',      label: '🌊 Drainage'      },
  { value: 'road_damage',   label: '🚧 Road Damage'   },
  { value: 'tree_hazard',   label: '🌳 Tree Hazard'   },
  { value: 'other',         label: '⚠️ Other'         },
];

const STATUS_OPTIONS = [
  { value: '',            label: 'All statuses' },
  { value: 'reported',    label: 'Reported'     },
  { value: 'verified',    label: 'Verified'     },
  { value: 'assigned',    label: 'Assigned'     },
  { value: 'in_progress', label: 'In Progress'  },
  { value: 'resolved',    label: 'Resolved'     },
  { value: 'disputed',    label: 'Disputed'     },
];

const SEVERITY_OPTIONS = [
  { value: '',         label: 'Any severity' },
  { value: 'critical', label: '🔴 Critical'  },
  { value: 'high',     label: '🟠 High'      },
  { value: 'medium',   label: '🟡 Medium'    },
  { value: 'low',      label: '🟢 Low'       },
];

// ── Component ────────────────────────────────────────────────
export default function SearchAndFilter() {
  const setIssues = useIssueStore((s) => s.setIssues);

  const [query,       setQuery]       = useState('');
  const [category,    setCategory]    = useState('');
  const [status,      setStatus]      = useState('');
  const [severity,    setSeverity]    = useState('');
  const [emergency,   setEmergency]   = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [isSearching, setIsSearching] = useState(false);

  const hasActiveFilters = Boolean(category || status || severity || emergency);

  // ── Apply filters ─────────────────────────────────────────
  const applySearch = useCallback(async () => {
    setIsSearching(true);
    try {
      const params: Record<string, string> = { per_page: '30' };
      if (category)  params.category     = category;
      if (status)    params.status       = status;
      if (severity)  params.severity     = severity;
      if (emergency) params.is_emergency = 'true';
      // Full-text query forwarded when backend supports it (Session 15)
      if (query.trim()) params.q         = query.trim();

      const data = await apiGet<PaginatedResponse<Issue>>('/issues', { params });
      setIssues(data);
    } catch {
      // Silently fail — existing issues remain visible on the map
    } finally {
      setIsSearching(false);
    }
  }, [category, status, severity, emergency, query, setIssues]);

  // ── Clear ─────────────────────────────────────────────────
  const clearFilters = useCallback(async () => {
    setQuery('');
    setCategory('');
    setStatus('');
    setSeverity('');
    setEmergency(false);
    setShowFilters(false);
    try {
      const data = await apiGet<PaginatedResponse<Issue>>('/issues', {
        params: { per_page: '30' },
      });
      setIssues(data);
    } catch {
      // ignore
    }
  }, [setIssues]);

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="space-y-2 w-full">
      {/* Search bar row */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search
            size={15}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none"
            aria-hidden="true"
          />
          <input
            id="search-input"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') applySearch();
            }}
            placeholder="Search issues…"
            className="
              w-full pl-9 pr-8 py-2.5
              bg-white dark:bg-gray-800
              border border-gray-200 dark:border-gray-700
              rounded-2xl text-sm text-gray-900 dark:text-white
              placeholder:text-gray-400 dark:placeholder:text-gray-500
              focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent
              transition-all
            "
            aria-label="Search community issues"
            aria-controls="search-results-region"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              aria-label="Clear search text"
            >
              <X size={12} />
            </button>
          )}
        </div>

        {/* Filter toggle button */}
        <button
          onClick={() => setShowFilters((v) => !v)}
          className={`
            p-2.5 rounded-2xl border flex-shrink-0 transition-all
            ${hasActiveFilters
              ? 'bg-primary-600 border-primary-600 text-white shadow-md shadow-primary-500/30'
              : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'}
          `}
          aria-label={`${showFilters ? 'Hide' : 'Show'} filters${hasActiveFilters ? ' (active)' : ''}`}
          aria-pressed={showFilters}
          aria-expanded={showFilters}
          aria-controls="filter-panel"
        >
          <SlidersHorizontal size={16} />
        </button>
      </div>

      {/* Collapsible filter panel */}
      {showFilters && (
        <div
          id="filter-panel"
          role="group"
          aria-label="Filter options"
          className="
            bg-white dark:bg-gray-800
            border border-gray-200 dark:border-gray-700
            rounded-2xl p-3.5 space-y-3
            shadow-lg shadow-black/5
          "
        >
          <div className="grid grid-cols-2 gap-2">
            {/* Category */}
            <div>
              <label
                htmlFor="filter-category"
                className="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide block mb-1"
              >
                Category
              </label>
              <select
                id="filter-category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="
                  w-full text-sm
                  bg-gray-50 dark:bg-gray-700
                  border border-gray-200 dark:border-gray-600
                  rounded-xl px-2.5 py-1.5
                  text-gray-900 dark:text-white
                  focus:outline-none focus:ring-2 focus:ring-primary-500
                "
              >
                {CATEGORY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            {/* Status */}
            <div>
              <label
                htmlFor="filter-status"
                className="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide block mb-1"
              >
                Status
              </label>
              <select
                id="filter-status"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="
                  w-full text-sm
                  bg-gray-50 dark:bg-gray-700
                  border border-gray-200 dark:border-gray-600
                  rounded-xl px-2.5 py-1.5
                  text-gray-900 dark:text-white
                  focus:outline-none focus:ring-2 focus:ring-primary-500
                "
              >
                {STATUS_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            {/* Severity */}
            <div>
              <label
                htmlFor="filter-severity"
                className="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide block mb-1"
              >
                Severity
              </label>
              <select
                id="filter-severity"
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
                className="
                  w-full text-sm
                  bg-gray-50 dark:bg-gray-700
                  border border-gray-200 dark:border-gray-600
                  rounded-xl px-2.5 py-1.5
                  text-gray-900 dark:text-white
                  focus:outline-none focus:ring-2 focus:ring-primary-500
                "
              >
                {SEVERITY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            {/* Emergency toggle */}
            <div className="flex flex-col justify-end">
              <label
                htmlFor="filter-emergency"
                className="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide block mb-1"
              >
                Emergency only
              </label>
              <button
                id="filter-emergency"
                role="switch"
                aria-checked={emergency}
                onClick={() => setEmergency((v) => !v)}
                className={`
                  relative inline-flex items-center w-10 h-5 rounded-full transition-colors
                  focus:outline-none focus:ring-2 focus:ring-primary-500
                  ${emergency ? 'bg-red-500' : 'bg-gray-300 dark:bg-gray-600'}
                `}
                aria-label="Show emergency issues only"
              >
                <span
                  className={`
                    inline-block w-4 h-4 bg-white rounded-full shadow
                    transform transition-transform
                    ${emergency ? 'translate-x-5' : 'translate-x-0.5'}
                  `}
                />
              </button>
            </div>
          </div>

          {/* Action row */}
          <div className="flex gap-2">
            <button
              onClick={applySearch}
              disabled={isSearching}
              className="
                flex-1 bg-gradient-to-r from-primary-600 to-violet-600
                hover:from-primary-700 hover:to-violet-700
                text-white text-sm font-semibold
                py-2 rounded-xl
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-all active:scale-[0.98]
              "
              aria-label="Apply selected filters"
            >
              {isSearching ? 'Searching…' : 'Apply Filters'}
            </button>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="
                  text-sm text-gray-500 dark:text-gray-400
                  hover:text-gray-700 dark:hover:text-gray-200
                  px-3 rounded-xl
                  hover:bg-gray-100 dark:hover:bg-gray-700
                  transition-colors
                "
                aria-label="Clear all active filters"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
