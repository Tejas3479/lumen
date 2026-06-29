import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Issue, IssueFilters, PaginatedResponse, StatusHistoryEntry } from '@/types';

interface IssueState {
  // Issue list
  issues: Issue[];
  totalIssues: number;
  currentPage: number;
  isLoading: boolean;
  error: string | null;
  filters: IssueFilters;

  // Selected issue
  selectedIssue: Issue | null;
  isDetailLoading: boolean;

  // Nearby issues for map
  nearbyIssues: Issue[];

  // Actions
  setIssues: (response: PaginatedResponse<Issue>) => void;
  appendIssues: (response: PaginatedResponse<Issue>) => void;
  setSelectedIssue: (issue: Issue | null) => void;
  updateIssue: (id: string, partial: Partial<Issue>) => void;
  addIssue: (issue: Issue) => void;
  setNearbyIssues: (issues: Issue[]) => void;
  setFilters: (filters: Partial<IssueFilters>) => void;
  resetFilters: () => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  // Socket-specific action aliases (descriptive names for useSocket.ts)
  addIssueFromSocket: (issue: Issue) => void;
  updateIssueStatusFromSocket: (
    id: string,
    status: Issue['status'],
    historyEntry: StatusHistoryEntry | null
  ) => void;
  updateAIResult: (
    id: string,
    result: Pick<Issue, 'ai_category' | 'ai_severity' | 'ai_confidence' | 'ai_explanation' | 'ai_summary' | 'ai_reasoning' | 'ai_alternatives'>
  ) => void;
  updateVerification: (id: string, count: number) => void;
}

const defaultFilters: IssueFilters = {
  page: 1,
  per_page: 20,
  sort_by: 'created_at',
  sort_dir: 'desc',
};

export const useIssueStore = create<IssueState>()(
  persist(
    (set, get) => ({
      issues: [],
      totalIssues: 0,
      currentPage: 1,
      isLoading: false,
      error: null,
      filters: defaultFilters,
      selectedIssue: null,
      isDetailLoading: false,
      nearbyIssues: [],

      setIssues: (response) =>
        set({
          issues: response.items,
          totalIssues: response.total,
          currentPage: response.page,
        }),

      appendIssues: (response) =>
        set((state) => ({
          issues: [...state.issues, ...response.items],
          totalIssues: response.total,
          currentPage: response.page,
        })),

      setSelectedIssue: (issue) => set({ selectedIssue: issue }),

      updateIssue: (id, partial) =>
        set((state) => ({
          issues: state.issues.map((i) => (i.id === id ? { ...i, ...partial } : i)),
          selectedIssue:
            state.selectedIssue?.id === id
              ? { ...state.selectedIssue, ...partial }
              : state.selectedIssue,
        })),

      addIssue: (issue) =>
        set((state) => ({
          issues: [issue, ...state.issues],
          totalIssues: state.totalIssues + 1,
        })),

      setNearbyIssues: (issues) => set({ nearbyIssues: issues }),

      setFilters: (filters) =>
        set((state) => ({
          filters: { ...state.filters, ...filters, page: 1 },
        })),

      resetFilters: () => set({ filters: defaultFilters }),

      setLoading: (loading) => set({ isLoading: loading }),

      setError: (error) => set({ error }),

      // ── Socket action aliases ───────────────────────────────────
      addIssueFromSocket: (issue) =>
        set((state) => ({
          issues: [issue, ...state.issues],
          totalIssues: state.totalIssues + 1,
          nearbyIssues: [issue, ...state.nearbyIssues],
        })),

      updateIssueStatusFromSocket: (id, status, historyEntry) =>
        set((state) => ({
          issues: state.issues.map((i) =>
            i.id === id
              ? {
                  ...i,
                  status,
                  status_history:
                    historyEntry && i.status_history
                      ? [...i.status_history, historyEntry]
                      : i.status_history,
                }
              : i
          ),
          selectedIssue:
            state.selectedIssue?.id === id
              ? {
                  ...state.selectedIssue,
                  status,
                  status_history:
                    historyEntry && state.selectedIssue.status_history
                      ? [...state.selectedIssue.status_history, historyEntry]
                      : state.selectedIssue.status_history,
                }
              : state.selectedIssue,
          nearbyIssues: state.nearbyIssues.map((i) =>
            i.id === id ? { ...i, status } : i
          ),
        })),

      updateAIResult: (id, result) =>
        set((state) => ({
          issues: state.issues.map((i) =>
            i.id === id ? { ...i, ...result } : i
          ),
          selectedIssue:
            state.selectedIssue?.id === id
              ? { ...state.selectedIssue, ...result }
              : state.selectedIssue,
        })),

      updateVerification: (id, count) =>
        set((state) => ({
          issues: state.issues.map((i) =>
            i.id === id ? { ...i, verification_count: count } : i
          ),
          selectedIssue:
            state.selectedIssue?.id === id
              ? { ...state.selectedIssue, verification_count: count }
              : state.selectedIssue,
        })),
    }),
    {
      name: 'lumen-issues',
      partialize: (state) => ({ filters: state.filters }),
    }
  )
);
