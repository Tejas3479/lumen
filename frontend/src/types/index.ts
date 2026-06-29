// =============================================================
// Lumen — Shared TypeScript Types
// Single source of truth. All types mirror the database schema.
// =============================================================

export type IssueStatus =
  | 'reported'
  | 'verified'
  | 'assigned'
  | 'in_progress'
  | 'resolved'
  | 'disputed'
  | 'closed';

export type IssueSeverity = 'low' | 'medium' | 'high' | 'critical';

export type MediaType = 'photo' | 'video' | 'voice';

export type VerificationType = 'hard' | 'soft';

export type VoteType = 'support' | 'duplicate' | 'emergency';

export type FlagReason =
  | 'spam'
  | 'duplicate'
  | 'inappropriate'
  | 'wrong_location'
  | 'resolved';

export type GamificationAction =
  | 'reported'
  | 'verified'
  | 'resolved_confirmed'
  | 'streak_bonus'
  | 'first_responder';

export type BadgeCategory =
  | 'reporting'
  | 'verification'
  | 'streak'
  | 'impact'
  | 'special';

export interface Category {
  id: string;
  name: string;
  display_name: string;
  icon: string;
  color: string;
  avg_resolution_days: number;
  is_active: boolean;
}

export interface IssueMedia {
  id: string;
  issue_id: string;
  media_type: MediaType;
  file_path: string;
  file_size: number;
  thumbnail_path: string | null;
  duration_seconds: number | null;
  uploaded_at: string;
}

export interface Issue {
  id: string;
  title: string;
  description: string;
  category_id: string;
  category?: Category;
  ai_category: string | null;
  ai_severity: IssueSeverity | null;
  ai_confidence: number | null;
  ai_explanation: string | null;
  ai_summary: string | null;
  ai_reasoning: string | null;                          // chain-of-thought from AI
  ai_alternatives: Record<string, number> | null;       // {category: confidence}
  user_correction: boolean;
  severity: IssueSeverity;
  status: IssueStatus;
  is_anonymous: boolean;
  is_emergency: boolean;
  reporter_id: string | null;
  reporter?: PublicUser | null;
  assigned_to: string | null;
  assignee?: PublicUser | null;
  latitude: number;
  longitude: number;
  address: string;
  ward: string | null;
  zone: string | null;
  vote_count: number;
  verification_count: number;
  view_count: number;
  resolution_notes: string | null;
  media: IssueMedia[];
  status_history?: StatusHistoryEntry[];
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  distance_meters?: number; // Added by nearby query
}

export interface StatusHistoryEntry {
  id: string;
  issue_id: string;
  from_status: IssueStatus | null;
  to_status: IssueStatus;
  changed_by: string | null;
  changed_by_user?: PublicUser | null;
  changed_at: string;
  note: string | null;
  is_official: boolean;
  is_public: boolean;
}

export interface Verification {
  id: string;
  issue_id: string;
  user_id: string;
  verification_type: VerificationType;
  distance_meters: number | null;
  comment: string | null;
  trust_weight: number;
  created_at: string;
}

export interface Comment {
  id: string;
  issue_id: string;
  user_id: string | null;
  parent_comment_id: string | null;
  content: string;
  is_official: boolean;
  is_pinned: boolean;
  is_deleted: boolean;
  user?: PublicUser | null;
  replies?: Comment[];
  created_at: string;
}

export interface Vote {
  id: string;
  issue_id: string;
  user_id: string | null;
  vote_type: VoteType;
  duplicate_of: string | null;
  created_at: string;
}

export interface Badge {
  id: string;
  name: string;
  display_name: string;
  description: string;
  icon: string;
  category: BadgeCategory;
  points_required: number | null;
}

export interface UserBadge {
  badge: Badge;
  earned_at: string;
}

export interface PredictiveHotspot {
  id: string;
  category: string;
  center_latitude: number;
  center_longitude: number;
  radius_meters: number;
  issue_count: number;
  predicted_next_issue_date: string | null;
  confidence: number;
  generated_at: string;
  ward: string | null;
}

export interface ResolutionFeedback {
  id: string;
  issue_id: string;
  submitted_by: string | null;
  is_resolved: boolean;
  comment: string | null;
  created_at: string;
}

// ─── User Types ───────────────────────────────────────────────

export interface User {
  id: string;
  email: string | null;
  username: string;
  display_name: string;
  is_guest: boolean;
  is_anonymous_default: boolean;
  is_admin: boolean;
  is_official: boolean;
  department: string | null;
  points: number;
  level: number;
  streak_days: number;
  pseudonym: string | null;
  privacy_settings: Record<string, unknown>;
  notification_preferences: Record<string, unknown>;
  created_at: string;
}

export interface PublicUser {
  id: string;
  display_name: string;
  pseudonym: string | null;
  points: number;
  level: number;
  is_official: boolean;
  department: string | null;
}

// ─── Auth Types ───────────────────────────────────────────────

export interface AuthTokens {
  access_token: string;
  token_type: string;
  user: User;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  username: string;
  display_name: string;
}

// ─── Report Form Types ────────────────────────────────────────

export interface ReportFormDraft {
  step: 1 | 2 | 3;
  category_id: string | null;
  category_name: string | null;
  title: string;
  description: string;
  is_emergency: boolean;
  is_anonymous: boolean;
  media_files: File[];
  latitude: number | null;
  longitude: number | null;
  address: string;
  idempotency_key: string; // UUID generated on form open
}

// ─── API Response Wrappers ────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface ApiError {
  error_code: string;
  message: string;
}

// ─── Analytics Types ──────────────────────────────────────────

export interface AnalyticsSummary {
  total_issues: number;
  resolved_issues: number;
  resolution_rate: number;
  avg_resolution_days: number;
  issues_by_category: Record<string, number>;
  issues_by_status: Record<string, number>;
  issues_by_severity: Record<string, number>;
  issues_by_ward: Record<string, number>;
  top_reporters: PublicUser[];
  trend_data: TrendDataPoint[];
}

export interface TrendDataPoint {
  date: string;
  reported: number;
  resolved: number;
}

export interface ImpactMetrics {
  user_id: string;
  issues_reported: number;
  issues_verified: number;
  issues_resolved: number;
  points: number;
  level: number;
  badges_earned: number;
  streak_days: number;
  impact_score: number;
}

// ─── Gamification Types ───────────────────────────────────────

export interface LeaderboardEntry {
  rank: number;
  user: PublicUser;
  points: number;
  issues_reported: number;
  issues_verified: number;
  badges_count: number;
  streak_days: number;
}

export interface GamificationEvent {
  action: GamificationAction;
  points_earned: number;
  new_total: number;
  new_level: number | null;
  badge_earned: Badge | null;
  message: string;
}

// ─── Filter / Query Types ─────────────────────────────────────

export interface IssueFilters {
  status?: IssueStatus[];
  severity?: IssueSeverity[];
  category_id?: string[];
  ward?: string;
  search?: string;
  lat?: number;
  lng?: number;
  radius_km?: number;
  page?: number;
  per_page?: number;
  sort_by?: 'created_at' | 'vote_count' | 'distance' | 'severity';
  sort_dir?: 'asc' | 'desc';
  date_from?: string;
  date_to?: string;
}

// ─── Offline Queue Types ──────────────────────────────────────

export interface OfflineDraft {
  id: string;
  created_at: string;
  payload: Omit<ReportFormDraft, 'media_files'>;
  media_blobs: string[]; // base64 encoded
  synced: boolean;
  sync_error: string | null;
}

// ─── Admin Types ──────────────────────────────────────────────

export interface AdminStats {
  total_users: number;
  active_users_today: number;
  total_issues: number;
  pending_moderation: number;
  spam_flagged: number;
  emergency_open: number;
}

export interface ModerationFlag {
  id: string;
  issue_id: string;
  flagged_by: string;
  reason: FlagReason;
  comment: string | null;
  is_resolved: boolean;
  created_at: string;
  issue?: Issue;
}

// ─── Socket Event Payloads ────────────────────────────────────

export interface SocketStatusUpdatePayload {
  issue_id: string;
  new_status: IssueStatus;
  history_entry: StatusHistoryEntry;
}

export interface SocketVerificationPayload {
  issue_id: string;
  verification_count: number;
  verification: Verification;
}

export interface SocketCommentPayload {
  issue_id: string;
  comment: Comment;
}

export interface SocketLeaderboardPayload {
  top_users: LeaderboardEntry[];
}

export interface SocketEmergencyPayload extends Issue {}

export interface SocketAIResultPayload {
  issue_id: string;
  ai_category: string;
  ai_severity: IssueSeverity;
  ai_confidence: number;
  ai_explanation: string;
  ai_summary: string;
  ai_reasoning: string | null;
  ai_alternatives: Record<string, number> | null;
}

export interface SocketHotspotPayload {
  hotspots: PredictiveHotspot[];
}

// ─── Analytics Dashboard Types ───────────────────────────────

export interface DashboardStats {
  total_issues: number;
  resolved_this_month: number;
  resolution_rate: number;
  avg_resolution_days: number;
  issues_by_category: Record<string, number>;
  issues_by_status: Record<string, number>;
  top_wards: Array<{ ward: string; count: number }>;
}

export interface ETAResponse {
  issue_id: string;
  estimated_days: number;
  estimated_resolution_date: string;
  confidence: 'low' | 'medium' | 'high';
  basis: string;
}
