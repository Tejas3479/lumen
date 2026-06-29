import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { useAppStore } from '@/store/appStore';
import { useSocket } from '@/hooks/useSocket';

// Global passive components
import GamificationToast from '@/components/GamificationToast';
import OfflineSyncBanner from '@/components/OfflineSyncBanner';
import LiveAIIndicator from '@/components/LiveAIIndicator';

// Pages
import HomePage from '@/pages/HomePage';
import IssueDetailPage from '@/pages/IssueDetailPage';
import LeaderboardPage from '@/pages/LeaderboardPage';
import ProfilePage from '@/pages/ProfilePage';
import ImpactDashboardPage from '@/pages/ImpactDashboardPage';
import AdminDashboardPage from '@/pages/AdminDashboardPage';
import PredictivePage from '@/pages/PredictivePage';
import NotFoundPage from '@/pages/NotFoundPage';

/**
 * Inner component so that useSocket runs inside BrowserRouter context.
 * Mounts the socket once for the full app lifetime.
 */
function AppContent() {
  // Initialise the global socket connection and all 13 event handlers.
  useSocket();

  return (
    <>
      {/* Sticky offline / sync banner — renders null when online + no drafts */}
      <OfflineSyncBanner />

      {/* Passive gamification toast listener */}
      <GamificationToast />

      {/* Thin header bar above routes */}
      <div className="sticky top-0 z-20 bg-white border-b border-gray-100 px-4 py-1.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-red-600">Lumen</span>
          <span className="text-xs text-gray-400 hidden sm:inline">Community Hero</span>
          {new URLSearchParams(window.location.search).get('demo') === 'true' && (
            <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">
              Demo Mode
            </span>
          )}
        </div>
        <LiveAIIndicator />
        <button
          onClick={() => {
            // Reset tour for judges
            localStorage.removeItem('lumen_tour_v2_complete');
            window.location.href = '/?judge=true';
          }}
          className="text-xs text-gray-400 hover:text-blue-600"
          aria-label="Restart feature tour"
        >
          Tour
        </button>
      </div>

      <Routes>
        <Route path="/"             element={<HomePage />} />
        <Route path="/issues/:id"   element={<IssueDetailPage />} />
        <Route path="/leaderboard"  element={<LeaderboardPage />} />
        <Route path="/profile"      element={<ProfilePage />} />
        <Route path="/profile/:id"  element={<ProfilePage />} />
        <Route path="/impact"       element={<ImpactDashboardPage />} />
        <Route path="/admin"        element={<AdminDashboardPage />} />
        <Route path="/admin/*"      element={<AdminDashboardPage />} />
        <Route path="/predictive"   element={<PredictivePage />} />
        <Route path="/predictions"  element={<PredictivePage />} />
        <Route path="*"             element={<NotFoundPage />} />
      </Routes>
    </>
  );
}

export default function App() {
  const isDark = useAppStore((s) => s.isDark);
  const fontSizeClass = useAppStore((s) => s.fontSizeClass);

  return (
    <div className={isDark ? 'dark' : ''}>
      <div id="main-content" className={`min-h-screen bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 ${fontSizeClass}`}>
        <BrowserRouter>
          <AppContent />
        </BrowserRouter>

        <Toaster
          position="top-center"
          gutter={8}
          toastOptions={{
            duration: 4000,
            style: {
              background:   isDark ? '#1e293b' : '#ffffff',
              color:        isDark ? '#f1f5f9' : '#0f172a',
              border:       `1px solid ${isDark ? '#334155' : '#e2e8f0'}`,
              borderRadius: '12px',
              fontSize:     '14px',
              fontFamily:   'Inter, system-ui, sans-serif',
            },
          }}
        />
      </div>
    </div>
  );
}
