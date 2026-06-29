import { NavLink } from 'react-router-dom';
import { Map, BarChart3, Trophy, User, Shield } from 'lucide-react';
import { useUserStore } from '@/store/userStore';

const NAV_ITEMS = [
  { to: '/',            icon: Map,       label: 'Map',     exact: true  },
  { to: '/impact',      icon: BarChart3, label: 'Impact',  exact: false },
  { to: '/leaderboard', icon: Trophy,    label: 'Leaders', exact: false },
  { to: '/profile',     icon: User,      label: 'Profile', exact: false },
];

export default function MobileBottomNav() {
  const { user } = useUserStore();

  return (
    <nav
      className="
        fixed bottom-0 left-0 right-0 z-30
        bg-white dark:bg-slate-900
        border-t border-slate-200 dark:border-slate-800
        flex items-center
        pb-safe
      "
      role="navigation"
      aria-label="Main navigation"
    >
      {NAV_ITEMS.map(({ to, icon: Icon, label, exact }) => (
        <NavLink
          key={to}
          to={to}
          end={exact}
          className={({ isActive }) =>
            [
              'flex-1 flex flex-col items-center justify-center',
              'py-2 gap-0.5 text-xs font-medium transition-colors',
              'min-h-[56px]',
              isActive
                ? 'text-blue-600 dark:text-blue-400'
                : 'text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300',
            ].join(' ')
          }
          aria-label={label}
        >
          {({ isActive }) => (
            <>
              <Icon
                size={22}
                aria-hidden="true"
                strokeWidth={isActive ? 2.5 : 1.5}
              />
              <span>{label}</span>
            </>
          )}
        </NavLink>
      ))}

      {/* Admin tab — only shown to admin or official users */}
      {(user?.is_admin || user?.is_official) && (
        <NavLink
          to="/admin"
          className={({ isActive }) =>
            [
              'flex-1 flex flex-col items-center justify-center',
              'py-2 gap-0.5 text-xs font-medium transition-colors min-h-[56px]',
              isActive
                ? 'text-red-600 dark:text-red-400'
                : 'text-slate-400 dark:text-slate-500',
            ].join(' ')
          }
          aria-label="Admin dashboard"
        >
          {({ isActive }) => (
            <>
              <Shield
                size={22}
                aria-hidden="true"
                strokeWidth={isActive ? 2.5 : 1.5}
              />
              <span>Admin</span>
            </>
          )}
        </NavLink>
      )}
    </nav>
  );
}
