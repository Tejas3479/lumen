import { io, type Socket } from 'socket.io-client';
import { useUserStore } from '@/store/userStore';

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:8000';

let socket: Socket | null = null;

export function getSocket(): Socket {
  if (!socket) {
    const token = useUserStore.getState().token;

    socket = io(SOCKET_URL, {
      autoConnect: false,
      transports: ['websocket', 'polling'],
      auth: token ? { token } : {},
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 30_000,
      timeout: 20_000,
    });
  }
  return socket;
}

export function connectSocket(): void {
  const s = getSocket();
  if (!s.connected) {
    s.connect();
  }
}

export function disconnectSocket(): void {
  if (socket?.connected) {
    socket.disconnect();
  }
}

export function joinIssueRoom(issueId: string): void {
  getSocket().emit('join_issue_room', { issue_id: issueId });
}

// Event name constants — must match backend LumenEvents class
export const SocketEvents = {
  NEW_ISSUE:                   'new_issue',
  ISSUE_UPDATED:               'issue_updated',
  STATUS_UPDATE:               'status_update',
  AI_RESULT:                   'ai_result',
  VERIFICATION_UPDATE:         'verification_update',
  COMMENT_ADDED:               'comment_added',
  LEADERBOARD_UPDATE:          'leaderboard_update',
  EMERGENCY_ALERT:             'emergency_alert',
  ISSUE_REOPENED:              'issue_reopened',
  RESOLUTION_FEEDBACK_RECEIVED:'resolution_feedback_received',
  OFFLINE_SYNC_COMPLETED:      'offline_sync_completed',
  ADMIN_ACTION:                'admin_action',
  HOTSPOT_UPDATE:              'hotspot_update',
} as const;

export type SocketEventName = (typeof SocketEvents)[keyof typeof SocketEvents];
