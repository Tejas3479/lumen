/**
 * GamificationToast
 *
 * Passive listener component — renders nothing in the DOM.
 * Subscribes to the 'lumen:gamification_event' custom DOM event
 * (dispatched by useSocket when the 'gamification_event' socket
 * event arrives) and shows styled toast notifications for:
 *
 *   • Points awarded  → blue card with +N pts
 *   • Badge unlocked  → amber card with badge icon
 *   • Level up        → purple card with star
 *
 * Mount once in App.tsx so it is always active regardless of route.
 */
import { useEffect } from 'react';
import toast from 'react-hot-toast';
import { TrendingUp, Star } from 'lucide-react';

interface GamificationEventDetail {
  action: string;
  points_awarded: number;
  total_points: number;
  badge_unlocked: {
    name: string;
    display_name: string;
    icon: string;
  } | null;
  new_level: number | null;
}

const ACTION_LABELS: Record<string, string> = {
  reported:           'Issue reported',
  verified:           'Issue verified',
  resolved_confirmed: 'Resolution confirmed',
  streak_bonus:       'Streak bonus',
  first_responder:    'First responder bonus',
};

export default function GamificationToast() {
  useEffect(() => {
    const handleEvent = (e: Event) => {
      const detail = (e as CustomEvent<GamificationEventDetail>).detail;
      const { action, points_awarded, badge_unlocked, new_level } = detail;

      // ── Points toast ──────────────────────────────────────────
      if (points_awarded > 0) {
        const label = ACTION_LABELS[action] ?? 'Action completed';
        toast.custom(
          (t) => (
            <div
              className={[
                'flex items-center gap-3 bg-white shadow-lg rounded-xl px-4 py-3',
                'border border-gray-100 max-w-xs w-full',
                t.visible ? 'animate-enter' : 'animate-leave',
              ].join(' ')}
              role="status"
              aria-live="polite"
              aria-label={`+${points_awarded} points for ${label}`}
            >
              <div className="w-9 h-9 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
                <TrendingUp size={18} className="text-blue-600" aria-hidden="true" />
              </div>
              <div>
                <div className="text-sm font-semibold text-gray-800">
                  +{points_awarded} points
                </div>
                <div className="text-xs text-gray-500">{label}</div>
              </div>
            </div>
          ),
          { duration: 3000, position: 'bottom-center' }
        );
      }

      // ── Badge unlocked toast ──────────────────────────────────
      if (badge_unlocked) {
        toast.custom(
          (t) => (
            <div
              className={[
                'flex items-center gap-3 bg-amber-50 shadow-lg rounded-xl px-4 py-3',
                'border border-amber-200 max-w-xs w-full',
                t.visible ? 'animate-enter' : 'animate-leave',
              ].join(' ')}
              role="status"
              aria-live="assertive"
              aria-label={`Badge unlocked: ${badge_unlocked.display_name}`}
            >
              {/* Badge emoji or fallback trophy */}
              <div className="w-9 h-9 bg-amber-100 rounded-full flex items-center justify-center flex-shrink-0 text-xl leading-none">
                {badge_unlocked.icon || '🏆'}
              </div>
              <div>
                <div className="text-xs font-semibold text-amber-700 uppercase tracking-wide">
                  Badge Unlocked!
                </div>
                <div className="text-sm font-bold text-amber-900">
                  {badge_unlocked.display_name}
                </div>
              </div>
            </div>
          ),
          { duration: 6000, position: 'bottom-center' }
        );
      }

      // ── Level up toast ────────────────────────────────────────
      if (new_level !== null && new_level !== undefined) {
        toast.custom(
          (t) => (
            <div
              className={[
                'flex items-center gap-3 bg-purple-50 shadow-lg rounded-xl px-4 py-3',
                'border border-purple-200 max-w-xs w-full',
                t.visible ? 'animate-enter' : 'animate-leave',
              ].join(' ')}
              role="status"
              aria-live="assertive"
              aria-label={`Level up! You are now level ${new_level}`}
            >
              <div className="w-9 h-9 bg-purple-100 rounded-full flex items-center justify-center flex-shrink-0">
                <Star size={18} className="text-purple-600" aria-hidden="true" />
              </div>
              <div>
                <div className="text-xs font-semibold text-purple-700 uppercase tracking-wide">
                  Level Up!
                </div>
                <div className="text-sm font-bold text-purple-900">
                  You reached Level {new_level}
                </div>
              </div>
            </div>
          ),
          { duration: 5000, position: 'bottom-center' }
        );
      }
    };

    window.addEventListener('lumen:gamification_event', handleEvent);
    return () =>
      window.removeEventListener('lumen:gamification_event', handleEvent);
  }, []);

  // Renders nothing — purely event-driven
  return null;
}
