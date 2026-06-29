/**
 * IssueDetailPage
 *
 * The "Track" screen — a full scrollable view of a single issue's lifecycle.
 * Loads in parallel: issue data, comments, and categories (for AI card context).
 * Renders: photo carousel → issue meta → AI card → resolution panel →
 *          verification panel → status timeline → assignment info →
 *          community comments → flag button.
 *
 * Real-time updates: store watcher picks up ai_result socket events and
 * patches local state without a full reload.
 */
import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Share2, Flag, ThumbsUp } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

import StatusTimeline from '@/components/StatusTimeline';
import AIExplanationCard from '@/components/AIExplanationCard';
import VerificationPanel from '@/components/VerificationPanel';
import ResolutionConfirmPanel from '@/components/ResolutionConfirmPanel';

import { useIssuesApi } from '@/hooks/useApi';
import { useUserStore } from '@/store/userStore';
import { useIssueStore } from '@/store/issueStore';
import { useIssueRoom } from '@/hooks/useIssueRoom';
import api from '@/lib/api';
import type { Issue, Category, Comment } from '@/types';

// ── Status display helpers ───────────────────────────────────────
const STATUS_LABELS: Record<string, string> = {
  reported: 'Reported',
  verified: 'Verified',
  assigned: 'Assigned',
  in_progress: 'In Progress',
  resolved: 'Resolved',
  disputed: 'Disputed',
  closed: 'Closed',
};

const STATUS_COLORS: Record<string, string> = {
  reported: 'bg-gray-100 text-gray-700',
  verified: 'bg-blue-100 text-blue-700',
  assigned: 'bg-purple-100 text-purple-700',
  in_progress: 'bg-amber-100 text-amber-700',
  resolved: 'bg-green-100 text-green-700',
  disputed: 'bg-red-100 text-red-700',
  closed: 'bg-gray-200 text-gray-500',
};

// ── Page component ───────────────────────────────────────────────
export default function IssueDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { fetchIssueById, supportIssue, flagIssue } = useIssuesApi();
  const { isAuthenticated } = useUserStore();
  const selectedIssue = useIssueStore((s) => s.selectedIssue);
  const setSelectedIssue = useIssueStore((s) => s.setSelectedIssue);

  const [issue, setIssue] = useState<Issue | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [newComment, setNewComment] = useState('');
  const [isPostingComment, setIsPostingComment] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [mediaIndex, setMediaIndex] = useState(0);
  const [aiTimedOut, setAiTimedOut] = useState(false);

  // Join the Socket.IO issue room for targeted real-time updates
  useIssueRoom(id);

  // ── Data loading ───────────────────────────────────────────────
  const loadIssue = useCallback(async () => {
    if (!id) return;
    setIsLoading(true);
    try {
      const [issueData, commentsData, categoriesData] = await Promise.all([
        fetchIssueById(id),
        api
          .get<Comment[]>(`/comments?issue_id=${id}`)
          .then((r) => r.data)
          .catch(() => [] as Comment[]),
        api
          .get<Category[]>('/analytics/categories')
          .then((r) => r.data)
          .catch(() => [] as Category[]),
      ]);

      setIssue(issueData);
      setComments(commentsData ?? []);
      setCategories(categoriesData ?? []);
      if (issueData) setSelectedIssue(issueData);
    } finally {
      setIsLoading(false);
    }
  }, [id, fetchIssueById, setSelectedIssue]);

  useEffect(() => {
    loadIssue();
  }, [loadIssue]);

  // ── Real-time AI result patch via store ────────────────────────
  // When the AI result socket event arrives, the issueStore is updated.
  // We mirror the AI fields into local state without a full reload.
  useEffect(() => {
    if (selectedIssue?.id === id && selectedIssue?.ai_category && issue) {
      setIssue((prev) =>
        prev
          ? {
              ...prev,
              ai_category: selectedIssue.ai_category,
              ai_severity: selectedIssue.ai_severity,
              ai_confidence: selectedIssue.ai_confidence,
              ai_explanation: selectedIssue.ai_explanation,
              ai_summary: selectedIssue.ai_summary,
            }
          : null
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIssue?.ai_category]);

  // ── AI polling with 60-second timeout ──────────────────────────
  // Polls GET /ai/status/{id} every 5 s for up to 12 attempts (60 s).
  // Stops immediately when ai_category arrives or timeout is reached.
  useEffect(() => {
    if (!issue || issue.ai_category) return;  // Already has AI result
    if (aiTimedOut) return;                    // Already timed out

    let attempts = 0;
    const MAX_ATTEMPTS = 12;  // 12 × 5 s = 60 seconds
    const INTERVAL_MS = 5000;

    const pollTimer = setInterval(async () => {
      attempts += 1;

      try {
        const aiStatus = await api.get<{
          issue_id: string;
          status?: string;
          ai_category?: string;
          ai_confidence?: number;
          ai_explanation?: string;
          ai_summary?: string;
          ai_severity?: string;
          ai_reasoning?: string;
          ai_alternatives?: Record<string, number>;
        }>(`/ai/status/${issue.id}`);

        if (aiStatus.data && aiStatus.data.ai_category) {
          // AI result arrived — update issue state
          setIssue((prev) => prev ? {
            ...prev,
            ai_category: aiStatus.data.ai_category || null,
            ai_confidence: aiStatus.data.ai_confidence || null,
            ai_explanation: aiStatus.data.ai_explanation || null,
            ai_summary: aiStatus.data.ai_summary || null,
            ai_severity: aiStatus.data.ai_severity as any || null,
            ai_reasoning: aiStatus.data.ai_reasoning || null,
            ai_alternatives: aiStatus.data.ai_alternatives || null,
          } : null);
          clearInterval(pollTimer);
        } else if (attempts >= MAX_ATTEMPTS) {
          // Timeout — give up polling
          setAiTimedOut(true);
          clearInterval(pollTimer);
        }
      } catch {
        // Network error during polling — keep trying until timeout
        if (attempts >= MAX_ATTEMPTS) {
          setAiTimedOut(true);
          clearInterval(pollTimer);
        }
      }
    }, INTERVAL_MS);

    return () => clearInterval(pollTimer);
  }, [issue?.id, issue?.ai_category, aiTimedOut]);

  // ── Real-time comment appending via socket ────────────────────
  // useSocket dispatches 'lumen:comment_added' DOM events.
  // We listen here so new comments appear instantly without a reload.
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as {
        issue_id: string;
        comment: Comment;
      };
      if (detail.issue_id !== id) return;
      setComments((prev) => {
        // Deduplicate by id (our own POST already appended it optimistically)
        if (prev.some((c) => c.id === detail.comment.id)) return prev;
        return [...prev, detail.comment];
      });
    };
    window.addEventListener('lumen:comment_added', handler);
    return () => window.removeEventListener('lumen:comment_added', handler);
  }, [id]);

  // ── Comment posting ────────────────────────────────────────────
  const handlePostComment = async () => {
    if (!newComment.trim() || !issue || !isAuthenticated) return;
    setIsPostingComment(true);
    try {
      const response = await api.post<Comment>('/comments', {
        issue_id: issue.id,
        content: newComment.trim(),
      });
      setComments((prev) => [...prev, response.data]);
      setNewComment('');
    } finally {
      setIsPostingComment(false);
    }
  };

  // ── Share handler ──────────────────────────────────────────────
  const handleShare = async () => {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title: issue?.title ?? 'Lumen Issue', url });
      } else {
        await navigator.clipboard.writeText(url);
      }
    } catch {
      // Share dialog cancelled or clipboard unavailable — silent fail
    }
  };

  // ── Loading skeleton ───────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="bg-white px-4 py-3 flex items-center gap-3 shadow-sm">
          <div className="w-8 h-8 bg-gray-200 rounded-full animate-pulse" aria-hidden="true" />
          <div className="flex-1 h-4 bg-gray-200 rounded animate-pulse" aria-hidden="true" />
        </div>
        <div className="p-4 space-y-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-16 bg-gray-200 rounded-xl animate-pulse"
              aria-hidden="true"
            />
          ))}
        </div>
        <span className="sr-only" role="status">
          Loading issue details…
        </span>
      </div>
    );
  }

  // ── 404 state ──────────────────────────────────────────────────
  if (!issue) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-500">Issue not found</p>
          <button
            onClick={() => navigate('/')}
            className="mt-3 text-blue-600 underline text-sm"
          >
            Back to map
          </button>
        </div>
      </div>
    );
  }

  // ── Main render ────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-50 pb-24">
      {/* ── Sticky header ── */}
      <div className="sticky top-0 z-10 bg-white shadow-sm">
        <div className="flex items-center gap-3 px-4 py-3">
          <button
            onClick={() => navigate(-1)}
            className="p-2 rounded-full hover:bg-gray-100 transition-colors"
            aria-label="Go back"
          >
            <ArrowLeft size={20} className="text-gray-700" />
          </button>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  STATUS_COLORS[issue.status] ?? STATUS_COLORS['reported']
                }`}
              >
                {STATUS_LABELS[issue.status] ?? issue.status}
              </span>
              {issue.is_emergency && (
                <span
                  className="text-xs font-semibold text-red-600"
                  role="status"
                  aria-label="Emergency issue"
                >
                  🚨 EMERGENCY
                </span>
              )}
            </div>
            <h1 className="text-sm font-semibold text-gray-900 truncate mt-0.5">
              {issue.title}
            </h1>
          </div>

          <button
            onClick={handleShare}
            className="p-2 rounded-full hover:bg-gray-100 transition-colors"
            aria-label="Share this issue"
          >
            <Share2 size={18} className="text-gray-500" />
          </button>
        </div>
      </div>

      <div className="px-4 py-4 space-y-5">
        {/* ── Photo carousel ── */}
        {issue.media && issue.media.length > 0 && (
          <div className="space-y-2">
            <div className="relative aspect-video rounded-xl overflow-hidden bg-gray-200">
              <img
                src={`/media/${issue.media[mediaIndex]?.file_path}`}
                alt={`Issue photo ${mediaIndex + 1} of ${issue.media.length}`}
                className="w-full h-full object-cover"
              />
              {issue.media.length > 1 && (
                <div className="absolute bottom-2 right-2 bg-black/50 text-white text-xs px-2 py-1 rounded-full">
                  {mediaIndex + 1}/{issue.media.length}
                </div>
              )}
            </div>

            {/* Thumbnail strip */}
            {issue.media.length > 1 && (
              <div
                className="flex gap-1.5 overflow-x-auto pb-1"
                role="group"
                aria-label="Photo thumbnails"
              >
                {issue.media.map((m, i) => (
                  <button
                    key={m.id}
                    onClick={() => setMediaIndex(i)}
                    className={`flex-shrink-0 w-12 h-12 rounded-lg overflow-hidden border-2 transition-all ${
                      i === mediaIndex
                        ? 'border-blue-500'
                        : 'border-transparent hover:border-gray-300'
                    }`}
                    aria-label={`View photo ${i + 1}`}
                    aria-pressed={i === mediaIndex}
                  >
                    <img
                      src={`/media/${m.thumbnail_path ?? m.file_path}`}
                      alt=""
                      className="w-full h-full object-cover"
                    />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Issue meta ── */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-gray-500 flex-wrap">
            <span>{issue.category?.display_name ?? issue.ai_category ?? 'Issue'}</span>
            <span aria-hidden="true">·</span>
            <span>{issue.address ?? issue.ward ?? 'Location unknown'}</span>
            <span aria-hidden="true">·</span>
            <span>
              {formatDistanceToNow(new Date(issue.created_at), {
                addSuffix: true,
              })}
            </span>
            {!issue.is_anonymous && issue.reporter && (
              <>
                <span aria-hidden="true">·</span>
                <span>
                  by {issue.reporter.pseudonym ?? issue.reporter.display_name}
                </span>
              </>
            )}
          </div>
          <p className="text-sm text-gray-700 leading-relaxed">
            {issue.description}
          </p>
        </div>

        {/* ── Stats row ── */}
        <div className="flex items-center gap-4 text-sm text-gray-600">
          <button
            onClick={() => supportIssue(issue.id)}
            className="flex items-center gap-1.5 hover:text-blue-600 transition-colors"
            aria-label={`${issue.vote_count} supporters. Tap to add your support.`}
          >
            <ThumbsUp size={16} aria-hidden="true" />
            <span>{issue.vote_count} supporting</span>
          </button>
          <span
            className="flex items-center gap-1.5"
            aria-label={`${issue.verification_count} verifications`}
          >
            <span aria-hidden="true">✓</span>
            <span>{issue.verification_count} verified</span>
          </span>
        </div>

        {/* ── AI Explanation Card (Session 7) ── */}
        <AIExplanationCard
          issue={issue}
          categories={categories}
          onCorrectionApplied={loadIssue}
          aiTimedOut={aiTimedOut}
        />

        {/* ── Resolution Confirmation Panel ── */}
        {issue.status === 'resolved' && (
          <ResolutionConfirmPanel
            issueId={issue.id}
            onFeedbackSubmitted={(isResolved) => {
              if (!isResolved) {
                // Optimistic: reflect disputed status immediately
                setIssue((prev) =>
                  prev ? { ...prev, status: 'disputed' } : null
                );
              }
            }}
          />
        )}

        {/* ── Verification Panel (Session 10) ── */}
        <VerificationPanel
          issue={issue}
          onVerified={(newCount) =>
            setIssue((prev) =>
              prev ? { ...prev, verification_count: newCount } : null
            )
          }
        />

        {/* ── Status Timeline ── */}
        <section aria-labelledby="timeline-heading">
          <h2
            id="timeline-heading"
            className="text-sm font-semibold text-gray-800 mb-3"
          >
            Status Timeline
          </h2>
          <StatusTimeline
            history={issue.status_history ?? []}
            currentStatus={issue.status as any}
          />
        </section>

        {/* ── Assignment info ── */}
        {issue.assignee && (
          <div className="bg-blue-50 rounded-xl px-4 py-3 text-xs text-blue-800">
            <span className="font-medium">Assigned to: </span>
            {issue.assignee.department ?? issue.assignee.display_name}
            {issue.assignee.department &&
              ` — ${issue.assignee.display_name}`}
          </div>
        )}

        {/* ── Community Comments ── */}
        <section aria-labelledby="comments-heading">
          <h2
            id="comments-heading"
            className="text-sm font-semibold text-gray-800 mb-3"
          >
            Community Discussion
          </h2>

          {comments.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-4">
              No comments yet. Be the first to add context.
            </p>
          ) : (
            <div className="space-y-3">
              {comments.map((comment) => (
                <div
                  key={comment.id}
                  className={`rounded-xl p-3 text-sm ${
                    comment.is_official
                      ? 'bg-blue-50 border border-blue-100'
                      : 'bg-white border border-gray-100'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="font-medium text-xs text-gray-800">
                      {comment.user?.pseudonym ??
                        comment.user?.display_name ??
                        'Citizen'}
                    </span>
                    {comment.is_official && (
                      <span className="text-xs bg-blue-600 text-white px-1.5 py-0.5 rounded font-medium">
                        Official
                      </span>
                    )}
                    {comment.is_pinned && (
                      <span className="text-xs text-amber-600">
                        📌 Pinned
                      </span>
                    )}
                    <span className="text-xs text-gray-400 ml-auto">
                      {formatDistanceToNow(new Date(comment.created_at), {
                        addSuffix: true,
                      })}
                    </span>
                  </div>
                  <p className="text-xs text-gray-700 leading-relaxed">
                    {comment.content}
                  </p>

                  {/* Depth-1 replies */}
                  {comment.replies && comment.replies.length > 0 && (
                    <div className="mt-2 ml-3 space-y-2 border-l-2 border-gray-100 pl-3">
                      {comment.replies.map((reply) => (
                        <div key={reply.id}>
                          <span className="text-xs font-medium text-gray-600">
                            {reply.user?.pseudonym ??
                              reply.user?.display_name ??
                              'Citizen'}
                          </span>
                          <p className="text-xs text-gray-600 leading-relaxed">
                            {reply.content}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Comment input */}
          {isAuthenticated ? (
            <div className="mt-3 flex gap-2">
              <textarea
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                placeholder="Add a comment or update…"
                rows={2}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
                aria-label="Write a comment"
                onKeyDown={(e) => {
                  // Cmd/Ctrl + Enter submits
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    handlePostComment();
                  }
                }}
              />
              <button
                onClick={handlePostComment}
                disabled={!newComment.trim() || isPostingComment}
                className="px-3 py-2 bg-blue-600 text-white rounded-xl text-xs font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed self-end transition-colors"
                aria-label="Post comment"
              >
                {isPostingComment ? '…' : 'Post'}
              </button>
            </div>
          ) : (
            <p className="text-xs text-center text-gray-400 mt-3">
              Sign in to add comments
            </p>
          )}
        </section>

        {/* ── Flag button ── */}
        <button
          onClick={() => flagIssue(issue.id, 'inappropriate')}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-red-500 transition-colors mx-auto"
          aria-label="Flag this issue as inappropriate or spam"
        >
          <Flag size={12} aria-hidden="true" />
          Flag this issue
        </button>
      </div>
    </div>
  );
}
