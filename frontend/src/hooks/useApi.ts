/**
 * Lumen useApi Hook
 *
 * Typed API call wrappers for all backend endpoints.
 * Uses the shared axios client from lib/api.ts which:
 *   - Attaches the JWT automatically from userStore
 *   - Handles 401/429/5xx globally with toasts
 *   - Returns unwrapped `response.data` via the apiPost/apiGet helpers
 *
 * Session 3: Auth calls fully implemented.
 * Other namespaces are typed stubs, filled in Sessions 4–17.
 */
import { useCallback } from 'react';
import { apiGet, apiPost } from '@/lib/api';
import api from '@/lib/api';
import { useUserStore } from '@/store/userStore';
import { useIssueStore } from '@/store/issueStore';
import type { AuthTokens, LoginPayload, RegisterPayload, User, Issue, PaginatedResponse, DashboardStats, ETAResponse } from '@/types';
import toast from 'react-hot-toast';

// ── Types local to this file ──────────────────────────────────

interface GuestSessionData {
  guest_session_id: string;
  access_token: string;
  token_type: string;
  message: string;
}

// ─────────────────────────────────────────────────────────────
// Auth API Hook
// ─────────────────────────────────────────────────────────────

export function useAuthApi() {
  const setAuth = useUserStore((s) => s.setAuth);
  const logout = useUserStore((s) => s.logout);
  const setGuestSession = useUserStore((s) => s.setGuestSession);

  /**
   * Register a new citizen account.
   * On success: stores the JWT in userStore and shows a welcome toast.
   * On failure: shows the server error message (e.g., email taken).
   */
  const register = useCallback(
    async (payload: RegisterPayload): Promise<AuthTokens | null> => {
      try {
        const data = await apiPost<AuthTokens>('/auth/register', payload);
        setAuth(data);
        toast.success(`Welcome, ${data.user.display_name}! 🎉`);
        return data;
      } catch (err: any) {
        const msg =
          err?.data?.detail?.message ||
          err?.message ||
          'Registration failed. Please try again.';
        toast.error(msg);
        return null;
      }
    },
    [setAuth],
  );

  /**
   * Authenticate with email + password.
   * On success: stores the JWT and shows a welcome-back toast.
   * On failure: shows the credential error (without revealing whether email exists).
   */
  const login = useCallback(
    async (payload: LoginPayload): Promise<AuthTokens | null> => {
      try {
        const data = await apiPost<AuthTokens>('/auth/login', payload);
        setAuth(data);
        toast.success(`Welcome back, ${data.user.display_name}!`);
        return data;
      } catch (err: any) {
        const msg =
          err?.data?.detail?.message ||
          err?.message ||
          'Login failed. Check your email and password.';
        toast.error(msg);
        return null;
      }
    },
    [setAuth],
  );

  /**
   * Create a guest session without an account.
   * The JWT is stored via setGuestSession so subsequent API calls
   * (e.g., issue reporting) are authenticated automatically.
   * Returns the guest_session_id for use as an offline sync idempotency key.
   */
  const continueAsGuest = useCallback(async (): Promise<string | null> => {
    try {
      const data = await apiPost<GuestSessionData>('/auth/guest');
      setGuestSession(data.guest_session_id, data.access_token);
      toast.success('Continuing as guest — you can still report issues.');
      return data.guest_session_id;
    } catch {
      toast.error('Could not start guest session. Please try again.');
      return null;
    }
  }, [setGuestSession]);

  /**
   * Log out the current user.
   * The server call is best-effort (logout is stateless — client discards JWT).
   * userStore is always cleared regardless of network outcome.
   */
  const logoutUser = useCallback(async (): Promise<void> => {
    try {
      await apiPost('/auth/logout');
    } catch {
      // Intentionally swallowed: logout is stateless, client clears regardless
    } finally {
      logout();
      toast.success('You have been logged out.');
    }
  }, [logout]);

  /**
   * Fetch the current authenticated user's profile.
   * Used on app startup to restore session state (validate stored token).
   * Returns null silently if the token is expired or invalid.
   */
  const getMe = useCallback(async (): Promise<User | null> => {
    try {
      return await apiGet<User>('/auth/me');
    } catch {
      return null;
    }
  }, []);

  return { register, login, continueAsGuest, logoutUser, getMe };
}

// ─────────────────────────────────────────────────────────────
// Issues API Hook
// ─────────────────────────────────────────────────────────────

export function useIssuesApi() {
  const setNearbyIssues = useIssueStore((s) => s.setNearbyIssues);
  const setIssues = useIssueStore((s) => s.setIssues);
  const addIssue = useIssueStore((s) => s.addIssue);
  const setLoading = useIssueStore((s) => s.setLoading);
  const setError = useIssueStore((s) => s.setError);

  /** Load issues near a map coordinate for the live map view. */
  const fetchNearby = useCallback(
    async (lat: number, lng: number, radius = 2000): Promise<Issue[]> => {
      try {
        const issues = await apiGet<Issue[]>('/issues/nearby', {
          params: { lat, lng, radius },
        });
        setNearbyIssues(issues);
        return issues;
      } catch {
        setError('Could not load nearby issues');
        return [];
      }
    },
    [setNearbyIssues, setError],
  );

  /** Paginated issue feed with optional filters. */
  const fetchIssues = useCallback(
    async (params?: Record<string, unknown>): Promise<PaginatedResponse<Issue> | null> => {
      setLoading(true);
      try {
        const data = await apiGet<PaginatedResponse<Issue>>('/issues', { params });
        setIssues(data);
        return data;
      } catch {
        setError('Could not load issues');
        return null;
      } finally {
        setLoading(false);
      }
    },
    [setIssues, setLoading, setError],
  );

  /** Fetch a single issue by ID. */
  const fetchIssueById = useCallback(async (id: string): Promise<Issue | null> => {
    try {
      return await apiGet<Issue>(`/issues/${id}`);
    } catch {
      return null;
    }
  }, []);

  /**
   * Submit a new civic issue report.
   * Uses multipart FormData so media files are included.
   */
  const submitReport = useCallback(
    async (formData: FormData): Promise<Issue | null> => {
      try {
        const issue = await api
          .post<Issue>('/issues', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
          .then((r) => r.data);
        addIssue(issue);
        toast.success('Report submitted! Your issue is now live on the map. 📍');
        return issue;
      } catch (err: any) {
        const msg =
          err?.data?.detail?.message ||
          err?.message ||
          'Failed to submit report. Please try again.';
        toast.error(msg);
        return null;
      }
    },
    [addIssue],
  );

  /** 'I see this too' support vote. */
  const supportIssue = useCallback(async (issueId: string): Promise<boolean> => {
    try {
      await apiPost(`/issues/${issueId}/support`, {
        issue_id: issueId,
        vote_type: 'support',
      });
      toast.success('Support added — your voice counts! 👍');
      return true;
    } catch (err: any) {
      const msg = err?.data?.detail?.message || 'Could not add support';
      toast.error(msg);
      return false;
    }
  }, []);

  /** Flag an issue for moderation. */
  const flagIssue = useCallback(
    async (issueId: string, reason: string, detail?: string): Promise<boolean> => {
      try {
        await apiPost(`/issues/${issueId}/flag`, { reason, detail });
        toast.success('Issue flagged for review');
        return true;
      } catch {
        toast.error('Could not flag issue');
        return false;
      }
    },
    [],
  );

  /** Confirm or dispute a resolution. */
  const submitResolutionFeedback = useCallback(
    async (issueId: string, isResolved: boolean, comment?: string): Promise<boolean> => {
      try {
        await apiPost(`/issues/${issueId}/resolution-feedback`, {
          is_resolved: isResolved,
          comment,
        });
        toast.success(
          isResolved
            ? 'Great! Thanks for confirming the fix. 🎉'
            : 'Feedback recorded. The issue will be reviewed again.',
        );
        return true;
      } catch {
        toast.error('Could not submit feedback');
        return false;
      }
    },
    [],
  );

  return {
    fetchNearby,
    fetchIssues,
    fetchIssueById,
    submitReport,
    supportIssue,
    flagIssue,
    submitResolutionFeedback,
  };
}

// ─────────────────────────────────────────────────────────────
// Verification API Hook — filled in Session 10
// ─────────────────────────────────────────────────────────────

export function useVerificationApi() {
  /**
   * Submits a community verification for an issue.
   *
   * @param issueId  UUID of the issue to verify.
   * @param type     'hard' (GPS presence required) or 'soft' (personal knowledge).
   * @param lat      User's GPS latitude — required for hard verification.
   * @param lng      User's GPS longitude — required for hard verification.
   * @param comment  Optional free-text comment from the verifier.
   * @returns        true if the verification was accepted, false on any error.
   */
  const verifyIssue = useCallback(
    async (
      issueId: string,
      type: 'hard' | 'soft',
      lat?: number,
      lng?: number,
      comment?: string,
    ): Promise<boolean> => {
      try {
        await api.post(`/issues/${issueId}/verify`, {
          verification_type: type,
          latitude: lat,
          longitude: lng,
          comment,
        });
        toast.success(
          type === 'hard'
            ? '✓ Hard verification recorded — thank you for being there! (+25 pts)'
            : '✓ Soft verification recorded — your local knowledge counts! (+10 pts)',
        );
        return true;
      } catch (err: any) {
        const msg =
          err?.response?.data?.message ||
          err?.response?.data?.detail?.message ||
          'Verification failed';
        toast.error(msg);
        return false;
      }
    },
    [],
  );

  return { verifyIssue };
}

// ───────────────────────────────────────────────────────────────
// Analytics API Hook — filled in Session 23
// ───────────────────────────────────────────────────────────────

export function useAnalyticsApi() {
  /**
   * Fetch aggregate stats for the Impact Dashboard.
   * Returns null on any network error so callers can show a skeleton.
   */
  const fetchDashboard = useCallback(async (): Promise<DashboardStats | null> => {
    try {
      return await apiGet<DashboardStats>('/analytics/dashboard');
    } catch {
      return null;
    }
  }, []);

  /**
   * Fetch the estimated resolution time for a specific issue.
   * Returns null if the issue doesn't exist or the ETA cannot be calculated.
   */
  const fetchETA = useCallback(async (issueId: string): Promise<ETAResponse | null> => {
    try {
      return await apiGet<ETAResponse>(`/analytics/eta/${issueId}`);
    } catch {
      return null;
    }
  }, []);

  /**
   * Fetch heatmap data points for the Leaflet heatmap layer.
   * Returns an empty array on error so the map renders without crashing.
   */
  const fetchHeatmap = useCallback(
    async (params?: { category?: string; ward?: string }): Promise<Array<{ lat: number; lng: number; weight: number }>> => {
      try {
        return await apiGet('/analytics/heatmap', { params });
      } catch {
        return [];
      }
    },
    [],
  );

  return { fetchDashboard, fetchETA, fetchHeatmap };
}

// ─────────────────────────────────────────────────────────────
// Gamification API Hook — filled in Session 17
// ─────────────────────────────────────────────────────────────

export function useGamificationApi() {
  return {};
}
