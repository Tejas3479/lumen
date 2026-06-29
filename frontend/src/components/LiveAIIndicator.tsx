import { useState, useEffect } from 'react';
import { Bot } from 'lucide-react';

export default function LiveAIIndicator() {
  const [isActive, setIsActive] = useState(false);
  const [lastActivity, setLastActivity] = useState<string | null>(null);

  useEffect(() => {
    // Listen for AI activity events from socket
    const handleAIResult = (e: CustomEvent) => {
      setIsActive(true);
      setLastActivity('Gemini classified an issue');
      setTimeout(() => setIsActive(false), 5000);
    };

    const handleTriageResult = () => {
      setIsActive(true);
      setLastActivity('Triage Agent reasoned about an issue');
      setTimeout(() => setIsActive(false), 5000);
    };

    // Also pulse when any socket event related to AI fires
    window.addEventListener('lumen:ai_result', handleAIResult as EventListener);
    window.addEventListener('lumen:triage_complete', handleTriageResult);

    // Hook into useSocket's ai_result handler to dispatch DOM event
    return () => {
      window.removeEventListener('lumen:ai_result', handleAIResult as EventListener);
      window.removeEventListener('lumen:triage_complete', handleTriageResult);
    };
  }, []);

  // Also pulse the indicator when the useSocket ai_result fires
  // Wire: in useSocket.ts, after updateAIResult(data.issue_id, data), add:
  // window.dispatchEvent(new CustomEvent('lumen:ai_result', { detail: data }));

  if (!isActive) {
    return (
      <div
        className="flex items-center gap-1 text-xs text-gray-400"
        aria-label="AI agents idle"
      >
        <Bot size={12} aria-hidden="true" />
        <span className="hidden sm:inline">AI Ready</span>
      </div>
    );
  }

  return (
    <div
      className="flex items-center gap-1.5 text-xs text-purple-600 font-medium"
      role="status"
      aria-live="polite"
      aria-label={`AI active: ${lastActivity}`}
    >
      <div className="w-2 h-2 bg-purple-500 rounded-full animate-pulse" aria-hidden="true" />
      <Bot size={12} aria-hidden="true" />
      <span className="hidden sm:inline truncate max-w-[120px]">{lastActivity}</span>
    </div>
  );
}
