import { useState, useEffect } from 'react';
import { useUserStore } from '@/store/userStore';
import { useNavigate } from 'react-router-dom';
import {
  Shield, Users, Flag, Download, AlertTriangle, ArrowLeft,
  BarChart3, RefreshCw,
} from 'lucide-react';
import AdminIssueQueue from '@/components/AdminIssueQueue';
import { apiGet, apiPatch } from '@/lib/api';
import toast from 'react-hot-toast';
import type { Issue } from '@/types';

type Tab = 'queue' | 'users' | 'flags';

interface AdminUser {
  id: string;
  email: string;
  username: string;
  display_name: string;
  is_admin: boolean;
  is_official: boolean;
  is_banned: boolean;
  department: string | null;
  points: number;
  level: number;
  created_at: string;
}

interface ModerationFlag {
  id: string;
  issue_id: string;
  flagged_by: string;
  reason: string;
  detail: string | null;
  status: string;
  created_at: string;
}

const TABS: { id: Tab; label: string; icon: typeof Shield }[] = [
  { id: 'queue',  label: 'Issue Queue', icon: BarChart3 },
  { id: 'users',  label: 'Users',       icon: Users     },
  { id: 'flags',  label: 'Flags',       icon: Flag      },
];

export default function AdminDashboardPage() {
  const { user } = useUserStore();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>('queue');

  // Users tab state
  const [userList, setUserList] = useState<AdminUser[]>([]);
  const [userSearch, setUserSearch] = useState('');
  const [usersLoading, setUsersLoading] = useState(false);

  // Flags tab state
  const [flags, setFlags] = useState<ModerationFlag[]>([]);
  const [flagsLoading, setFlagsLoading] = useState(false);

  // Access guard
  if (!user?.is_admin && !user?.is_official) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900">
        <div className="text-center space-y-4">
          <div className="w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center mx-auto">
            <Shield size={28} className="text-red-500" />
          </div>
          <h1 className="text-lg font-bold text-slate-800 dark:text-slate-200">
            Admin Access Required
          </h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm">
            You don't have permission to view this page.
          </p>
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 mx-auto text-blue-600 dark:text-blue-400
                       hover:underline text-sm font-medium"
          >
            <ArrowLeft size={14} />
            Back to map
          </button>
        </div>
      </div>
    );
  }

  const loadUsers = async (search = '') => {
    setUsersLoading(true);
    try {
      const params: Record<string, string> = { page: '1', per_page: '50' };
      if (search) params.search = search;
      const data = await apiGet<{ items: AdminUser[] }>('/admin/users', { params });
      setUserList(data.items);
    } catch {
      toast.error('Failed to load users');
    } finally {
      setUsersLoading(false);
    }
  };

  const loadFlags = async () => {
    setFlagsLoading(true);
    try {
      const data = await apiGet<{ items: ModerationFlag[] }>('/admin/flags');
      setFlags(data.items ?? []);
    } catch {
      toast.error('Failed to load flags');
    } finally {
      setFlagsLoading(false);
    }
  };

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    if (tab === 'users' && userList.length === 0) loadUsers();
    if (tab === 'flags' && flags.length === 0) loadFlags();
  };

  const moderateUser = async (userId: string, action: { is_banned?: boolean; is_official?: boolean }) => {
    try {
      await apiPatch(`/admin/users/${userId}/moderate`, action);
      toast.success('User updated');
      loadUsers(userSearch);
    } catch {
      toast.error('Moderation action failed');
    }
  };

  const reviewFlag = async (flagId: string, status: 'reviewed' | 'dismissed') => {
    try {
      await apiPatch(`/admin/flags/${flagId}`, { status });
      toast.success(status === 'dismissed' ? 'Flag dismissed' : 'Flag reviewed');
      setFlags((prev) => prev.filter((f) => f.id !== flagId));
    } catch {
      toast.error('Flag review failed');
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* Header */}
      <header className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center gap-3">
          <div className="w-9 h-9 bg-red-100 dark:bg-red-900/30 rounded-xl flex items-center justify-center">
            <Shield size={18} className="text-red-500" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              Admin Dashboard
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {user?.display_name} · {user?.department || (user?.is_admin ? 'Super Admin' : 'Official')}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {user?.is_admin && (
              <span className="px-2.5 py-1 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400
                               text-xs font-semibold rounded-full">
                Admin
              </span>
            )}
            {user?.is_official && !user?.is_admin && (
              <span className="px-2.5 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400
                               text-xs font-semibold rounded-full">
                Official
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Tab navigation */}
      <div className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 px-6">
        <div className="max-w-7xl mx-auto flex gap-1" role="tablist">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              role="tab"
              id={`tab-${id}`}
              aria-selected={activeTab === id}
              aria-controls={`panel-${id}`}
              onClick={() => handleTabChange(id)}
              className={[
                'flex items-center gap-2 py-3.5 px-4 text-sm font-medium border-b-2 transition-colors',
                activeTab === id
                  ? 'border-blue-600 text-blue-600 dark:text-blue-400 dark:border-blue-400'
                  : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300',
              ].join(' ')}
            >
              <Icon size={15} aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab panels */}
      <main className="px-4 sm:px-6 py-6 max-w-7xl mx-auto" role="tabpanel" id={`panel-${activeTab}`}>
        {/* ── Issue Queue ── */}
        {activeTab === 'queue' && (
          <AdminIssueQueue
            onIssueSelect={(issue: Issue) => navigate(`/issues/${issue.id}`)}
          />
        )}

        {/* ── Users ── */}
        {activeTab === 'users' && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <input
                type="search"
                placeholder="Search by email, username, or name…"
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadUsers(userSearch)}
                className="flex-1 text-sm border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2
                           bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200
                           placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                aria-label="Search users"
              />
              <button
                onClick={() => loadUsers(userSearch)}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg
                           hover:bg-blue-700 transition-colors"
                aria-label="Search"
              >
                <RefreshCw size={14} />
                Search
              </button>
            </div>

            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
              {/* Header row */}
              <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-4 px-4 py-2.5
                              bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800
                              text-xs font-medium text-slate-500 dark:text-slate-400">
                <span>User</span>
                <span>Level</span>
                <span>Role</span>
                <span>Status</span>
                <span>Actions</span>
              </div>

              {usersLoading ? (
                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="h-14 px-4 py-3 flex items-center" aria-hidden="true">
                      <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded animate-pulse w-2/3" />
                    </div>
                  ))}
                </div>
              ) : userList.length === 0 ? (
                <div className="text-center py-12 text-slate-400 text-sm">
                  {userSearch ? 'No users found' : 'Click Search to load users'}
                </div>
              ) : (
                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                  {userList.map((u) => (
                    <div
                      key={u.id}
                      className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-4 px-4 py-3 items-center
                                 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
                          {u.display_name}
                        </p>
                        <p className="text-xs text-slate-400 dark:text-slate-500 truncate">
                          @{u.username} · {u.email}
                        </p>
                      </div>
                      <span className="text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                        Lv {u.level}
                      </span>
                      <span className="text-xs">
                        {u.is_admin ? (
                          <span className="px-2 py-0.5 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-full">
                            Admin
                          </span>
                        ) : u.is_official ? (
                          <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-full">
                            Official
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-500 rounded-full">
                            Citizen
                          </span>
                        )}
                      </span>
                      <span className={`text-xs font-medium ${
                        u.is_banned
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-emerald-600 dark:text-emerald-400'
                      }`}>
                        {u.is_banned ? 'Banned' : 'Active'}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => moderateUser(u.id, { is_banned: !u.is_banned })}
                          className={`text-xs px-2.5 py-1 rounded-lg transition-colors font-medium ${
                            u.is_banned
                              ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-200'
                              : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 hover:bg-red-200'
                          }`}
                          aria-label={u.is_banned ? 'Unban user' : 'Ban user'}
                        >
                          {u.is_banned ? 'Unban' : 'Ban'}
                        </button>
                        {!u.is_official && !u.is_admin && (
                          <button
                            onClick={() => moderateUser(u.id, { is_official: true })}
                            className="text-xs px-2.5 py-1 rounded-lg bg-blue-100 dark:bg-blue-900/30
                                       text-blue-700 dark:text-blue-400 hover:bg-blue-200 transition-colors font-medium"
                            aria-label="Promote to official"
                          >
                            + Official
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Flags ── */}
        {activeTab === 'flags' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                Pending Moderation Flags
              </h2>
              <button
                onClick={loadFlags}
                className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400
                           hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
                aria-label="Refresh flags"
              >
                <RefreshCw size={13} />
                Refresh
              </button>
            </div>

            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
              {flagsLoading ? (
                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="h-14 px-4 py-3 flex items-center" aria-hidden="true">
                      <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded animate-pulse w-3/4" />
                    </div>
                  ))}
                </div>
              ) : flags.length === 0 ? (
                <div className="text-center py-12 text-slate-400 dark:text-slate-500 text-sm">
                  No pending flags 🎉
                </div>
              ) : (
                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                  {flags.map((flag) => (
                    <div
                      key={flag.id}
                      className="flex items-center gap-4 px-4 py-3
                                 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <AlertTriangle size={12} className="text-amber-500 flex-shrink-0" aria-hidden="true" />
                          <span className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
                            {flag.reason.replace('_', ' ')}
                          </span>
                        </div>
                        {flag.detail && (
                          <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5 truncate">
                            {flag.detail}
                          </p>
                        )}
                        <p className="text-xs text-slate-400 dark:text-slate-500">
                          Issue: {flag.issue_id.slice(0, 8)}…
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => reviewFlag(flag.id, 'reviewed')}
                          className="text-xs px-2.5 py-1 rounded-lg bg-emerald-100 dark:bg-emerald-900/30
                                     text-emerald-700 dark:text-emerald-400 hover:bg-emerald-200 transition-colors font-medium"
                          aria-label="Mark flag as reviewed"
                        >
                          Reviewed
                        </button>
                        <button
                          onClick={() => reviewFlag(flag.id, 'dismissed')}
                          className="text-xs px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800
                                     text-slate-600 dark:text-slate-400 hover:bg-slate-200 transition-colors font-medium"
                          aria-label="Dismiss flag"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
