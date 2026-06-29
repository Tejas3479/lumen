/**
 * useIssueRoom
 *
 * Manages joining and leaving a Socket.IO room for a specific issue.
 * Call from IssueDetailPage — the room ensures that comment_added,
 * verification_update, and status_update events are routed only to
 * clients actually viewing this issue (targeted emission on the server).
 *
 * Room name pattern: "issue_{issue_id}"
 */
import { useEffect } from 'react';
import { getSocket } from '@/lib/socket';

/**
 * @param issueId  UUID of the issue being viewed.
 *                 Pass undefined while loading to avoid premature join.
 */
export function useIssueRoom(issueId: string | undefined): void {
  useEffect(() => {
    if (!issueId) return;

    const socket = getSocket();

    // Tell the server to add this client to the issue-specific room
    socket.emit('join_issue_room', { issue_id: issueId });

    return () => {
      // Leave the room when the user navigates away from the detail page
      socket.emit('leave_issue_room', { issue_id: issueId });
    };
  }, [issueId]);
}
