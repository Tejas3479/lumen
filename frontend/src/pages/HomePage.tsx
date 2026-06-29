/**
 * HomePage — Primary app view: fullscreen map + FAB + issue feed drawer.
 *
 * Layout (mobile-first):
 * - Full viewport map (Leaflet)
 * - Floating header with search + theme toggle
 * - FAB (bottom-right) — opens ReportIssueModal
 * - Tapping a marker opens IssueBottomSheet
 * - Slide-up feed drawer (partial) for browsing issues below the map
 */
import { useState, useEffect, useCallback } from 'react';
import { Plus, MapPin, List, Search, Bell } from 'lucide-react';

import MapView from '@/components/MapView';
import IssueBottomSheet from '@/components/IssueBottomSheet';
import ReportIssueModal from '@/components/ReportIssueModal';
import IssueCard from '@/components/IssueCard';
import MobileBottomNav from '@/components/MobileBottomNav';
import OfflineSyncBanner from '@/components/OfflineSyncBanner';
import ThemeToggle from '@/components/ThemeToggle';
import OnboardingTour from '@/components/OnboardingTour';
import AboutDemoModal from '@/components/AboutDemoModal';

import { useIssuesApi } from '@/hooks/useApi';
import { useGeolocation } from '@/hooks/useGeolocation';
import { useOfflineQueue } from '@/hooks/useOfflineQueue';
import { useIssueStore } from '@/store/issueStore';
import { useUserStore } from '@/store/userStore';
import { useAuthApi } from '@/hooks/useApi';
import type { Category, Issue } from '@/types';
import { apiGet } from '@/lib/api';

type FeedView = 'map' | 'list';

export default function HomePage() {
  const { fetchNearby } = useIssuesApi();
  const { getMe } = useAuthApi();
  const { location } = useGeolocation();
  const { loadDrafts } = useOfflineQueue();
  const nearbyIssues = useIssueStore((s) => s.nearbyIssues);
  const isLoading = useIssueStore((s) => s.isLoading);
  const setUser = useUserStore((s) => s.setUser);
  const isAuthenticated = useUserStore((s) => s.isAuthenticated);

  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [categories, setCategories] = useState<Category[]>([]);
  const [feedView, setFeedView] = useState<FeedView>('map');
  const [feedOpen, setFeedOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [aboutOpen, setAboutOpen] = useState(false);

  // Restore session on mount
  useEffect(() => {
    if (isAuthenticated) {
      getMe().then((user) => {
        if (user) setUser(user);
      });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Load categories for the report modal
  useEffect(() => {
    apiGet<Category[]>('/categories').then(setCategories).catch(() => {});
  }, []);

  // Load offline drafts from IndexedDB on mount (Session 19)
  useEffect(() => { loadDrafts(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Initial nearby fetch when GPS resolves, with fallback to Bengaluru
  useEffect(() => {
    if (location?.latitude) {
      fetchNearby(location.latitude, location.longitude, 3000);
    } else {
      fetchNearby(12.9716, 77.5946, 5000); // Bengaluru
    }
  }, [location?.latitude, location?.longitude]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('demo') === 'true') {
      // Auto-open the first emergency issue for demo mode
      const emergencyIssue = nearbyIssues.find((i) => i.is_emergency);
      if (emergencyIssue) {
        // Simulate clicking the first emergency marker
        setTimeout(() => setSelectedIssue(emergencyIssue), 2000);
      }
    }
  }, [nearbyIssues]);

  const handleMarkerClick = useCallback((issue: Issue) => {
    setSelectedIssue(issue);
  }, []);

  const filteredIssues = nearbyIssues.filter((issue) =>
    !searchQuery ||
    issue.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    issue.description.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div className="flex flex-col h-screen bg-slate-50 dark:bg-slate-950 overflow-hidden">
      <OfflineSyncBanner />

      {/* ── Floating header ── */}
      <header
        className="absolute top-0 left-0 right-0 z-30 px-4 pt-3 pb-2 pointer-events-none"
        role="banner"
      >
        <div className="flex items-center gap-2 pointer-events-auto">
          {/* Brand */}
          <div className="flex items-center gap-2 px-3 py-2 rounded-2xl glass shadow-lg">
            <MapPin className="text-primary-500" size={18} />
            <span className="font-black text-slate-900 dark:text-white text-base tracking-tight">
              Lumen
            </span>
          </div>

          {/* Search bar */}
          <div className="flex-1 relative">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
            />
            <input
              type="search"
              placeholder="Search issues..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-2 text-sm rounded-2xl glass shadow-lg border border-white/20 dark:border-slate-700/50 outline-none focus:ring-2 focus:ring-primary-400 bg-white/90 dark:bg-slate-900/90 text-slate-900 dark:text-white placeholder:text-slate-400"
            />
          </div>

          {/* Theme toggle */}
          <div className="glass rounded-2xl shadow-lg">
            <ThemeToggle />
          </div>

          {/* About Demo button */}
          <button
            onClick={() => setAboutOpen(true)}
            className="glass px-3 py-2 rounded-2xl shadow-lg border border-white/20 dark:border-slate-700/50 pointer-events-auto text-xs font-bold text-slate-800 dark:text-slate-100 hover:text-primary-650 dark:hover:text-primary-400 bg-white/95 dark:bg-slate-900/95 transition-colors flex items-center justify-center whitespace-nowrap"
            aria-label="About this demo"
          >
            ℹ️ Demo Info
          </button>
        </div>

        {/* Map / List toggle */}
        <div className="flex mt-2 bg-white/90 dark:bg-slate-900/90 backdrop-blur rounded-2xl p-1 shadow-lg w-fit pointer-events-auto">
          {(['map', 'list'] as FeedView[]).map((v) => (
            <button
              key={v}
              onClick={() => setFeedView(v)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                feedView === v
                  ? 'bg-primary-500 text-white shadow'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
              }`}
            >
              {v === 'map' ? <MapPin size={12} /> : <List size={12} />}
              {v.charAt(0).toUpperCase() + v.slice(1)}
            </button>
          ))}
        </div>
      </header>

      {/* ── Map (always rendered, hidden behind list when list view active) ── */}
      <main className="flex-1 relative" role="main">
        <div
          className={`absolute inset-0 transition-opacity duration-300 ${
            feedView === 'map' ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
          }`}
        >
          <MapView
            issues={filteredIssues}
            onIssueSelect={handleMarkerClick}
            center={
              location?.latitude !== null && location?.longitude !== null && location?.latitude !== undefined
                ? [location.latitude, location.longitude]
                : [12.9716, 77.5946]
            }
          />
        </div>

        {/* ── List view ── */}
        <div
          className={`absolute inset-0 overflow-y-auto bg-slate-50 dark:bg-slate-950 transition-opacity duration-300 ${
            feedView === 'list' ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
          }`}
        >
          {/* Top padding for header */}
          <div className="h-28" />
          <div className="px-4 pb-24 space-y-2">
            {isLoading && (
              <div className="flex justify-center py-8">
                <div className="w-8 h-8 border-2 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
              </div>
            )}

            {!isLoading && filteredIssues.length === 0 && (
              <div className="text-center py-16">
                <div className="w-16 h-16 bg-primary-100 dark:bg-primary-900/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <MapPin className="text-primary-500" size={28} />
                </div>
                <h2 className="font-bold text-slate-900 dark:text-white mb-1">
                  {searchQuery ? 'No matching issues' : 'No issues nearby'}
                </h2>
                <p className="text-sm text-slate-400 dark:text-slate-500 mb-5">
                  {searchQuery
                    ? 'Try a different search term'
                    : 'Be the first to report a civic issue in your area!'}
                </p>
                <button
                  onClick={() => setReportOpen(true)}
                  className="btn btn-primary px-6 py-2.5 text-sm"
                >
                  Report an Issue
                </button>
              </div>
            )}

            {filteredIssues.map((issue) => (
              <IssueCard
                key={issue.id}
                issue={issue}
                showDistance
                onClick={() => setSelectedIssue(issue)}
              />
            ))}
          </div>
        </div>

        {/* ── Issue count pill (map view) ── */}
        {feedView === 'map' && nearbyIssues.length > 0 && (
          <button
            onClick={() => setFeedOpen((o) => !o)}
            className="absolute bottom-24 left-1/2 -translate-x-1/2 z-20 px-4 py-2 rounded-full glass shadow-lg text-xs font-semibold text-slate-700 dark:text-slate-200 flex items-center gap-2 hover:scale-105 transition-transform"
          >
            <span className="w-2 h-2 rounded-full bg-primary-500 animate-pulse" />
            {nearbyIssues.length} issues nearby
          </button>
        )}
      </main>

      {/* ── FAB — Report Issue ── */}
      <button
        id="fab-report-issue"
        onClick={() => setReportOpen(true)}
        aria-label="Report a civic issue"
        className="fixed bottom-20 right-4 z-30 w-14 h-14 rounded-2xl bg-gradient-to-br from-primary-500 to-violet-600 text-white shadow-xl hover:shadow-primary-500/40 hover:scale-110 active:scale-95 transition-all duration-200 flex items-center justify-center"
      >
        <Plus size={24} strokeWidth={2.5} />
      </button>

      {/* ── Bottom nav ── */}
      <MobileBottomNav />

      {/* ── Modals & Sheets ── */}
      <AboutDemoModal
        isOpen={aboutOpen}
        onClose={() => setAboutOpen(false)}
      />

      <ReportIssueModal
        isOpen={reportOpen}
        onClose={() => setReportOpen(false)}
        categories={categories}
      />

      {selectedIssue && (
        <IssueBottomSheet
          issue={selectedIssue}
          onClose={() => setSelectedIssue(null)}
        />
      )}

      {/* Session 18: First-time user onboarding tour */}
      <OnboardingTour />
    </div>
  );
}
