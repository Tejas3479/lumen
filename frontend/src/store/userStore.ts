import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, AuthTokens } from '@/types';

interface UserState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isGuest: boolean;
  guestSessionId: string | null;

  // Actions
  setAuth: (tokens: AuthTokens) => void;
  setUser: (user: User) => void;
  setGuestSession: (guestSessionId: string, token: string) => void;
  logout: () => void;
  updatePoints: (points: number, level: number) => void;
  incrementStreak: () => void;
  /** Merge a partial user object into the stored user (used by socket events). */
  updateUser: (partial: Partial<User>) => void;
}

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      isGuest: false,
      guestSessionId: null,

      setAuth: (tokens) =>
        set({
          token: tokens.access_token,
          user: tokens.user,
          isAuthenticated: true,
          isGuest: tokens.user.is_guest,
        }),

      setUser: (user) => set({ user }),

      setGuestSession: (guestSessionId, token) =>
        set({
          token,
          guestSessionId,
          isAuthenticated: true,
          isGuest: true,
        }),

      logout: () =>
        set({
          user: null,
          token: null,
          isAuthenticated: false,
          isGuest: false,
          guestSessionId: null,
        }),

      updatePoints: (points, level) =>
        set((state) => ({
          user: state.user ? { ...state.user, points, level } : null,
        })),

      incrementStreak: () =>
        set((state) => ({
          user: state.user
            ? { ...state.user, streak_days: state.user.streak_days + 1 }
            : null,
        })),

      updateUser: (partial) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...partial } : null,
        })),
    }),
    {
      name: 'lumen-user',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
        isGuest: state.isGuest,
        guestSessionId: state.guestSessionId,
      }),
    }
  )
);
