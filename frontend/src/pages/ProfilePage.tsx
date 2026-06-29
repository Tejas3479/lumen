import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  User, Star, Flame, CheckCircle, Flag, Shield, Settings,
  ArrowLeft, Trophy, Zap, Monitor,
} from 'lucide-react';
import { apiGet, apiPatch } from '@/lib/api';
import { useUserStore } from '@/store/userStore';
import type { User as UserType } from '@/types';
import MobileBottomNav from '@/components/MobileBottomNav';
import ThemeToggle from '@/components/ThemeToggle';
import toast from 'react-hot-toast';

interface UserStats {
  user_id: string;
  display_name: string;
  pseudonym: string | null;
  points: number;
  level: number;
  points_to_next_level: number;
  streak_days: number;
  issues_reported: number;
  verifications: number;
  issues_resolved: number;
  badges: Array<{
    badge: {
      id: string;
      name: string;
      display_name: string;
      description: string;
      icon: string;
      category: string;
    };
    earned_at: string;
  }>;
}

interface SettingsFormData {
  display_name: string;
  pseudonym: string;
  is_anonymous_default: boolean;
}

function StatPill({ icon: Icon, value, label, color }: {
  icon: typeof User;
  value: number | string;
  label: string;
  color: string;
}) {
  return (
    <div className={`flex flex-col items-center gap-1 bg-white dark:bg-slate-900 
                     rounded-2xl px-4 py-3 border border-slate-100 dark:border-slate-800 shadow-sm`}>
      <Icon size={16} className={color} aria-hidden="true" />
      <span className="text-lg font-bold text-slate-900 dark:text-slate-100">
        {typeof value === 'number' ? value.toLocaleString() : value}
      </span>
      <span className="text-xs text-slate-500 dark:text-slate-400 text-center leading-tight">
        {label}
      </span>
    </div>
  );
}

function BadgeCard({ badge, earnedAt }: {
  badge: UserStats['badges'][0]['badge'];
  earnedAt: string;
}) {
  return (
    <div
      className="bg-white dark:bg-slate-900 rounded-2xl p-3 border border-slate-100 dark:border-slate-800
                 shadow-sm flex flex-col items-center gap-2 text-center"
      title={badge.description}
    >
      <div className="text-2xl" aria-hidden="true">{badge.icon}</div>
      <div>
        <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 leading-tight">
          {badge.display_name}
        </p>
        <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
          {new Date(earnedAt).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}
        </p>
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const { id: profileUserId } = useParams<{ id?: string }>();
  const { user: currentUser, token, updateUser } = useUserStore();
  const navigate = useNavigate();

  const viewingOwnProfile = !profileUserId || profileUserId === currentUser?.id;
  const targetUserId = profileUserId || currentUser?.id;

  const [stats, setStats] = useState<UserStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [settingsForm, setSettingsForm] = useState<SettingsFormData>({
    display_name: currentUser?.display_name ?? '',
    pseudonym: currentUser?.pseudonym ?? '',
    is_anonymous_default: currentUser?.is_anonymous_default ?? false,
  });
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!targetUserId) return;
    setIsLoading(true);
    const endpoint = viewingOwnProfile
      ? '/gamification/me'
      : `/gamification/users/${targetUserId}`;
    apiGet<UserStats>(endpoint)
      .then((data) => {
        setStats(data);
        if (viewingOwnProfile) {
          setSettingsForm({
            display_name: data.display_name,
            pseudonym: data.pseudonym ?? '',
            is_anonymous_default: currentUser?.is_anonymous_default ?? false,
          });
        }
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [targetUserId, viewingOwnProfile]);

  const saveSettings = async () => {
    setIsSaving(true);
    try {
      const updated = await apiPatch<UserType>('/users/me/settings', {
        display_name: settingsForm.display_name || undefined,
        pseudonym: settingsForm.pseudonym || undefined,
        is_anonymous_default: settingsForm.is_anonymous_default,
      });
      updateUser(updated);
      setShowSettings(false);
      toast.success('Settings saved');
    } catch {
      toast.error('Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  };

  if (!currentUser && !profileUserId) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center">
        <div className="text-center space-y-3">
          <User size={40} className="text-slate-200 dark:text-slate-700 mx-auto" />
          <p className="text-slate-500 dark:text-slate-400 text-sm">
            Sign in to see your profile
          </p>
          <button
            onClick={() => navigate('/')}
            className="text-blue-600 dark:text-blue-400 text-sm hover:underline"
          >
            Back to map
          </button>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 pb-24" aria-busy="true">
        <div className="h-48 bg-gradient-to-br from-blue-500 to-purple-600 animate-pulse" />
        <div className="px-4 space-y-4 mt-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 bg-slate-200 dark:bg-slate-800 rounded-2xl animate-pulse" />
          ))}
        </div>
        <span className="sr-only" role="status">Loading profile…</span>
        <MobileBottomNav />
      </div>
    );
  }

  const displayName = stats?.pseudonym || stats?.display_name || 'Anonymous';
  const level = stats?.level ?? 1;
  const levelProgress = stats
    ? Math.max(0, Math.min(100, ((stats.points % (level * 100)) / (level * 100)) * 100))
    : 0;

  return (
    <main className="min-h-screen bg-slate-50 dark:bg-slate-950 pb-24">
      {/* Hero header */}
      <div className="relative bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-700 px-4 pt-12 pb-16 text-white">
        {!viewingOwnProfile && (
          <button
            onClick={() => navigate(-1)}
            className="absolute top-4 left-4 flex items-center gap-1 text-white/80 text-sm hover:text-white"
            aria-label="Go back"
          >
            <ArrowLeft size={16} />
            Back
          </button>
        )}

        {viewingOwnProfile && (
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center
                       bg-white/20 rounded-xl hover:bg-white/30 transition-colors"
            aria-label="Open settings"
            aria-expanded={showSettings}
          >
            <Settings size={16} />
          </button>
        )}

        {/* Avatar */}
        <div className="w-20 h-20 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center
                        border-2 border-white/30 mx-auto mb-3">
          <User size={36} className="text-white/90" />
        </div>

        <div className="text-center">
          <h1 className="text-xl font-bold">{displayName}</h1>
          {currentUser?.is_official && (
            <div className="flex items-center justify-center gap-1.5 mt-1">
              <Shield size={13} className="text-blue-200" />
              <span className="text-blue-200 text-xs font-medium">
                {currentUser.department || 'Official'}
              </span>
            </div>
          )}

          {/* Level + XP bar */}
          <div className="mt-3 max-w-xs mx-auto">
            <div className="flex items-center justify-between text-xs text-white/70 mb-1.5">
              <span className="flex items-center gap-1">
                <Zap size={10} />
                Level {level}
              </span>
              <span>
                {stats?.points_to_next_level ?? 0} pts to Lv {level + 1}
              </span>
            </div>
            <div className="h-2 bg-white/20 rounded-full overflow-hidden">
              <div
                className="h-full bg-white/80 rounded-full transition-all duration-1000"
                style={{ width: `${levelProgress}%` }}
                role="progressbar"
                aria-valuenow={levelProgress}
                aria-valuemax={100}
                aria-label={`Level progress: ${Math.round(levelProgress)}%`}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Stats row */}
      <div className="px-4 -mt-8 mb-5">
        <div className="grid grid-cols-4 gap-2">
          <StatPill
            icon={Flag}
            value={stats?.issues_reported ?? 0}
            label="Reported"
            color="text-blue-500"
          />
          <StatPill
            icon={CheckCircle}
            value={stats?.verifications ?? 0}
            label="Verified"
            color="text-emerald-500"
          />
          <StatPill
            icon={Trophy}
            value={stats?.issues_resolved ?? 0}
            label="Resolved"
            color="text-amber-500"
          />
          <StatPill
            icon={Flame}
            value={stats?.streak_days ? `${stats.streak_days}d` : '—'}
            label="Streak"
            color="text-orange-500"
          />
        </div>
      </div>

      <div className="px-4 space-y-5 max-w-2xl mx-auto">
        {/* Settings panel (own profile only) */}
        {viewingOwnProfile && showSettings && (
          <section
            className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-100 dark:border-slate-800 shadow-sm space-y-4"
            aria-labelledby="settings-heading"
          >
            <h2 id="settings-heading" className="text-sm font-bold text-slate-800 dark:text-slate-200 flex items-center gap-2">
              <Settings size={14} />
              Account Settings
            </h2>

            <div className="space-y-3">
              <div>
                <label
                  className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1"
                  htmlFor="display-name"
                >
                  Display Name
                </label>
                <input
                  id="display-name"
                  type="text"
                  value={settingsForm.display_name}
                  onChange={(e) => setSettingsForm((f) => ({ ...f, display_name: e.target.value }))}
                  className="w-full text-sm border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2
                             bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200
                             focus:outline-none focus:ring-2 focus:ring-blue-500"
                  maxLength={128}
                />
              </div>

              <div>
                <label
                  className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1"
                  htmlFor="pseudonym"
                >
                  Pseudonym (shown on leaderboard)
                </label>
                <input
                  id="pseudonym"
                  type="text"
                  value={settingsForm.pseudonym}
                  onChange={(e) => setSettingsForm((f) => ({ ...f, pseudonym: e.target.value }))}
                  className="w-full text-sm border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2
                             bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200
                             focus:outline-none focus:ring-2 focus:ring-blue-500"
                  maxLength={64}
                  placeholder="Optional — leave blank to show real name"
                />
              </div>

              <label className="flex items-center gap-3 cursor-pointer" htmlFor="anon-default">
                <input
                  id="anon-default"
                  type="checkbox"
                  checked={settingsForm.is_anonymous_default}
                  onChange={(e) => setSettingsForm((f) => ({ ...f, is_anonymous_default: e.target.checked }))}
                  className="w-4 h-4 accent-blue-600 rounded"
                />
                <span className="text-sm text-slate-700 dark:text-slate-300">
                  Report issues anonymously by default
                </span>
              </label>
            </div>

            <div className="flex gap-2">
              <button
                onClick={saveSettings}
                disabled={isSaving}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium
                           py-2 rounded-xl transition-colors disabled:opacity-50"
                aria-label="Save settings"
              >
                {isSaving ? 'Saving…' : 'Save Settings'}
              </button>
              <button
                onClick={() => setShowSettings(false)}
                className="px-4 border border-slate-200 dark:border-slate-700 text-sm text-slate-600
                           dark:text-slate-400 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                aria-label="Cancel"
              >
                Cancel
              </button>
            </div>
          </section>
        )}

        {/* Badges */}
        {stats && stats.badges.length > 0 && (
          <section aria-labelledby="badges-heading">
            <h2
              id="badges-heading"
              className="text-sm font-bold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2"
            >
              <Star size={14} className="text-amber-500" />
              Badges ({stats.badges.length})
            </h2>
            <div className="grid grid-cols-3 sm:grid-cols-4 gap-2" role="list">
              {stats.badges.map(({ badge, earned_at }) => (
                <div key={badge.id} role="listitem">
                  <BadgeCard badge={badge} earnedAt={earned_at} />
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Empty badge state */}
        {stats && stats.badges.length === 0 && (
          <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-100 dark:border-slate-800
                          text-center shadow-sm">
            <Star size={28} className="text-slate-200 dark:text-slate-700 mx-auto mb-3" />
            <p className="text-sm text-slate-400 dark:text-slate-500">
              No badges yet — start reporting to earn your first!
            </p>
          </div>
        )}

        {/* Display Settings — own profile only */}
        {viewingOwnProfile && (
          <section
            aria-labelledby="display-settings-heading"
            className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-100 dark:border-slate-800 shadow-sm"
          >
            <h2
              id="display-settings-heading"
              className="text-sm font-bold text-slate-800 dark:text-slate-200 flex items-center gap-2 mb-4"
            >
              <Monitor size={14} className="text-blue-500" aria-hidden="true" />
              Display Settings
            </h2>
            <ThemeToggle />
          </section>
        )}

        {/* Points breakdown */}
        {stats && (
          <section
            className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-100 dark:border-slate-800 shadow-sm"
            aria-labelledby="points-heading"
          >
            <h2
              id="points-heading"
              className="text-sm font-bold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2"
            >
              <Trophy size={14} className="text-amber-500" />
              Point Summary
            </h2>
            <div className="space-y-2.5">
              {[
                { label: 'Issues Reported',   pts: stats.issues_reported * 10,    hint: '10 pts each' },
                { label: 'Verifications',      pts: stats.verifications * 5,       hint: '5 pts each' },
                { label: 'Issues Resolved',    pts: stats.issues_resolved * 25,    hint: '25 pts each' },
              ].map(({ label, pts, hint }) => (
                <div key={label} className="flex items-center justify-between">
                  <div>
                    <span className="text-xs font-medium text-slate-700 dark:text-slate-300">{label}</span>
                    <span className="text-xs text-slate-400 dark:text-slate-500 ml-1.5">({hint})</span>
                  </div>
                  <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    +{pts.toLocaleString()}
                  </span>
                </div>
              ))}
              <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <span className="text-sm font-bold text-slate-800 dark:text-slate-200">Total</span>
                <span className="text-base font-bold text-blue-600 dark:text-blue-400">
                  {stats.points.toLocaleString()} pts
                </span>
              </div>
            </div>
          </section>
        )}
      </div>

      <MobileBottomNav />
    </main>
  );
}
