import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { PredictiveHotspot, Category } from '@/types';

/** Offline draft pending upload — fully implemented in Session 19 (PWA). */
export interface PendingDraft {
  idempotency_key: string;
  created_at: string;
  sync_status: 'pending' | 'syncing' | 'failed';
  draft: {
    title?: string;
    description: string;
    category_id?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    address?: string;
    is_anonymous?: boolean;
    is_emergency?: boolean;
  };
}

export type FontSizeClass = 'text-sm' | 'text-base' | 'text-lg' | 'text-xl';

interface AppState {
  // Theme
  isDark: boolean;
  toggleDark: () => void;

  // Accessibility — high contrast
  isHighContrast: boolean;
  toggleHighContrast: () => void;

  // Accessibility — font size
  fontSizeClass: FontSizeClass;
  setFontSize: (size: FontSizeClass) => void;

  // Map state
  mapCenter: [number, number];
  mapZoom: number;
  setMapCenter: (center: [number, number]) => void;
  setMapZoom: (zoom: number) => void;
  mapProvider: 'google' | 'leaflet';
  setMapProvider: (provider: 'google' | 'leaflet') => void;
  toggleMapProvider: () => void;

  // Global UI state
  isReportModalOpen: boolean;
  openReportModal: () => void;
  closeReportModal: () => void;

  isOnline: boolean;
  setOnline: (online: boolean) => void;

  // Categories (cached from API)
  categories: Category[];
  setCategories: (categories: Category[]) => void;

  // Hotspots
  hotspots: PredictiveHotspot[];
  setHotspots: (hotspots: PredictiveHotspot[]) => void;

  // Socket connection status
  isSocketConnected: boolean;
  setSocketConnected: (connected: boolean) => void;

  // Offline queue count
  offlineQueueCount: number;
  setOfflineQueueCount: (count: number) => void;

  // Pending offline drafts (Session 19 populates these)
  pendingDrafts: PendingDraft[];
  removePendingDraft: (key: string) => void;
  updateDraftStatus: (key: string, status: PendingDraft['sync_status']) => void;
  addPendingDraft: (draft: PendingDraft) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // Theme — default dark for civic feel
      isDark: true,
      toggleDark: () => set((state) => ({ isDark: !state.isDark })),

      // High contrast
      isHighContrast: false,
      toggleHighContrast: () =>
        set((state) => {
          const next = !state.isHighContrast;
          if (next) {
            document.body.classList.add('high-contrast');
          } else {
            document.body.classList.remove('high-contrast');
          }
          return { isHighContrast: next };
        }),

      // Font size
      fontSizeClass: 'text-base',
      setFontSize: (size) =>
        set(() => {
          // Apply CSS class to body immediately
          document.body.classList.remove('font-sm', 'font-base', 'font-lg', 'font-xl');
          document.body.classList.add(`font-${size.replace('text-', '')}`);
          return { fontSizeClass: size };
        }),

      // Map defaults — Bengaluru, India
      mapCenter: [12.9716, 77.5946],
      mapZoom: 13,
      setMapCenter: (center) => set({ mapCenter: center }),
      setMapZoom: (zoom) => set({ mapZoom: zoom }),
      mapProvider: 'google',
      setMapProvider: (provider) => set({ mapProvider: provider }),
      toggleMapProvider: () => set((state) => ({ mapProvider: state.mapProvider === 'google' ? 'leaflet' : 'google' })),

      // Report modal
      isReportModalOpen: false,
      openReportModal: () => set({ isReportModalOpen: true }),
      closeReportModal: () => set({ isReportModalOpen: false }),

      // Network
      isOnline: true,
      setOnline: (online) => set({ isOnline: online }),

      // Categories
      categories: [],
      setCategories: (categories) => set({ categories }),

      // Hotspots
      hotspots: [],
      setHotspots: (hotspots) => set({ hotspots }),

      // Socket
      isSocketConnected: false,
      setSocketConnected: (connected) => set({ isSocketConnected: connected }),

      // Offline queue
      offlineQueueCount: 0,
      setOfflineQueueCount: (count) => set({ offlineQueueCount: count }),

      // Pending drafts (Session 19)
      pendingDrafts: [],
      removePendingDraft: (key) =>
        set((state) => ({
          pendingDrafts: state.pendingDrafts.filter((d) => d.idempotency_key !== key),
        })),
      updateDraftStatus: (key, status) =>
        set((state) => ({
          pendingDrafts: state.pendingDrafts.map((d) =>
            d.idempotency_key === key ? { ...d, sync_status: status } : d
          ),
        })),
      addPendingDraft: (draft) =>
        set((state) => ({
          pendingDrafts: [...state.pendingDrafts, draft],
        })),
    }),
    {
      name: 'lumen-app',
      partialize: (state) => ({
        isDark: state.isDark,
        isHighContrast: state.isHighContrast,
        fontSizeClass: state.fontSizeClass,
        mapCenter: state.mapCenter,
        mapZoom: state.mapZoom,
        mapProvider: state.mapProvider,
      }),
      onRehydrateStorage: () => (state) => {
        // Re-apply persisted a11y classes after page load
        if (state?.isHighContrast) {
          document.body.classList.add('high-contrast');
        }
        if (state?.fontSizeClass) {
          document.body.classList.remove('font-sm', 'font-base', 'font-lg', 'font-xl');
          document.body.classList.add(`font-${state.fontSizeClass.replace('text-', '')}`);
        }
      },
    }
  )
);
