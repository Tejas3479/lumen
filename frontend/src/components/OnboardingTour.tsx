import { useState, useEffect, useCallback } from 'react';
import { X, MapPin, Camera, CheckCircle, Bot, Shield, Wifi, ChevronRight, ChevronLeft } from 'lucide-react';

interface TourStep {
  id: string;
  title: string;
  description: string;
  icon: React.ElementType;
  iconColor: string;
  highlight?: string;         // CSS selector of element to highlight
  action?: {                  // Optional auto-navigation
    label: string;
    href: string;
  };
  judgeNote?: string;         // Italic note for judges: "Watch for..."
}

const JUDGE_TOUR_STEPS: TourStep[] = [
  {
    id: 'report',
    title: 'Report in 60 seconds',
    description: 'Tap the red Report Issue button. Take a photo. The AI categorizes it automatically using Google Gemini.',
    icon: Camera,
    iconColor: 'text-red-500',
    judgeNote: 'Watch for: AI category + severity + reasoning appear within 5 seconds of submission.',
  },
  {
    id: 'ai',
    title: 'Google Gemini AI Analysis',
    description: 'After submitting, open any issue. The blue "AI detected" card shows Gemini\'s category, confidence, reasoning, and alternative categories considered.',
    icon: Bot,
    iconColor: 'text-blue-500',
    judgeNote: 'Watch for: "See AI reasoning" expander showing step-by-step Gemini chain-of-thought.',
  },
  {
    id: 'agents',
    title: '3 Autonomous AI Agents',
    description: 'Lumen runs agents that work without any human trigger. The Triage Agent reasons about every new issue. The Escalation Agent detects stalled issues every 30 minutes.',
    icon: Shield,
    iconColor: 'text-purple-500',
    action: { label: 'See agent status →', href: '/api/ai/agents/status' },
    judgeNote: 'Watch for: Admin queue shows 🤖 department badge + priority on each issue.',
  },
  {
    id: 'verify',
    title: 'Community Verification',
    description: 'Citizens verify issues with "I\'m here now" (GPS-checked) or "I know this exists" (no GPS needed). 2 hard verifications auto-upgrade status to Verified.',
    icon: CheckCircle,
    iconColor: 'text-green-500',
    judgeNote: 'Watch for: Verification count badge updates in real-time without page refresh.',
  },
  {
    id: 'offline',
    title: 'Works Offline',
    description: 'Open DevTools → Network → Offline. Try submitting a report. It saves to IndexedDB. Go back online — it syncs automatically.',
    icon: Wifi,
    iconColor: 'text-amber-500',
    judgeNote: 'Watch for: Amber banner shows pending count. Disappears when sync completes.',
  },
  {
    id: 'admin',
    title: 'Admin Dashboard',
    description: 'Login as admin@lumen.civic / admin123. The queue shows AI triage recommendations on every issue. Change a status — the timeline updates live in the citizen view.',
    icon: Shield,
    iconColor: 'text-gray-700',
    action: { label: 'Open admin →', href: '/admin' },
    judgeNote: 'Watch for: Status change in admin → instant timeline update in issue detail (WebSocket).',
  },
];

const STORAGE_KEY = 'lumen_tour_v2_complete';

export default function OnboardingTour() {
  const [isVisible, setIsVisible] = useState(false);
  const [step, setStep] = useState(0);
  const [isJudgeMode, setIsJudgeMode] = useState(false);

  const getActionHref = (href: string) => {
    if (href.startsWith('/api/')) {
      const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      return `${baseUrl}${href.substring(4)}`;
    }
    return href;
  };

  useEffect(() => {
    // Check for ?demo=true or ?judge=true URL params
    const params = new URLSearchParams(window.location.search);
    const forceShow = params.get('demo') === 'true' || params.get('judge') === 'true';
    const done = localStorage.getItem(STORAGE_KEY);

    if (forceShow) {
      setIsJudgeMode(true);
      setIsVisible(true);
      setStep(0);
    } else if (!done) {
      const timer = setTimeout(() => setIsVisible(true), 1500);
      return () => clearTimeout(timer);
    }
  }, []);

  const dismiss = useCallback(() => {
    setIsVisible(false);
    localStorage.setItem(STORAGE_KEY, 'true');
  }, []);

  const next = useCallback(() => {
    if (step < JUDGE_TOUR_STEPS.length - 1) {
      setStep((s) => s + 1);
    } else {
      dismiss();
    }
  }, [step, dismiss]);

  const prev = useCallback(() => {
    if (step > 0) setStep((s) => s - 1);
  }, [step]);

  if (!isVisible) return null;

  const current = JUDGE_TOUR_STEPS[step];
  const { icon: Icon } = current;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 z-50"
        onClick={dismiss}
        aria-hidden="true"
      />

      <div
        className="fixed bottom-20 left-4 right-4 z-50 bg-white rounded-2xl shadow-2xl overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-label={`Feature tour step ${step + 1} of ${JUDGE_TOUR_STEPS.length}: ${current.title}`}
        aria-live="polite"
        style={{ maxWidth: '480px', margin: '0 auto' }}
      >
        {/* Progress bar */}
        <div className="h-1 bg-gray-100">
          <div
            className="h-1 bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-300"
            style={{ width: `${((step + 1) / JUDGE_TOUR_STEPS.length) * 100}%` }}
            aria-hidden="true"
          />
        </div>

        <div className="p-5">
          {/* Header */}
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gray-50 rounded-full flex items-center justify-center flex-shrink-0">
                <Icon size={20} className={current.iconColor} aria-hidden="true" />
              </div>
              <div>
                <div className="text-xs text-gray-400 font-medium">
                  {step + 1} of {JUDGE_TOUR_STEPS.length}
                </div>
                <h2 className="text-base font-bold text-gray-900">{current.title}</h2>
              </div>
            </div>
            <button
              onClick={dismiss}
              className="p-1.5 rounded-full hover:bg-gray-100 flex-shrink-0"
              aria-label="Close tour"
            >
              <X size={16} className="text-gray-400" />
            </button>
          </div>

          {/* Description */}
          <p className="text-sm text-gray-600 leading-relaxed mb-3">
            {current.description}
          </p>

          {/* Judge note */}
          {current.judgeNote && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 mb-4">
              <p className="text-xs text-amber-800 italic">
                <span className="font-semibold not-italic">👀 Look for: </span>
                {current.judgeNote}
              </p>
            </div>
          )}

          {/* Optional action link */}
          {current.action && (
            <a
              href={getActionHref(current.action.href)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-blue-600 font-medium mb-4 hover:underline"
              aria-label={current.action.label}
            >
              {current.action.label}
            </a>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between">
            <button
              onClick={prev}
              disabled={step === 0}
              className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-600 disabled:opacity-0"
              aria-label="Previous feature"
            >
              <ChevronLeft size={16} />
              Back
            </button>

            {/* Dot indicators */}
            <div className="flex gap-1" aria-hidden="true">
              {JUDGE_TOUR_STEPS.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setStep(i)}
                  className={`rounded-full transition-all ${
                    i === step ? 'w-4 h-1.5 bg-blue-600' : 'w-1.5 h-1.5 bg-gray-300'
                  }`}
                  aria-label={`Go to step ${i + 1}`}
                />
              ))}
            </div>

            <button
              onClick={next}
              className="flex items-center gap-1 bg-blue-600 text-white text-sm font-semibold px-4 py-2 rounded-xl hover:bg-blue-700"
              aria-label={step < JUDGE_TOUR_STEPS.length - 1 ? 'Next feature' : 'Start exploring'}
            >
              {step < JUDGE_TOUR_STEPS.length - 1 ? 'Next' : 'Explore'}
              <ChevronRight size={14} />
            </button>
          </div>

          {/* Skip option */}
          <button
            onClick={dismiss}
            className="w-full text-center text-xs text-gray-400 hover:text-gray-600 mt-3"
            aria-label="Skip the feature tour"
          >
            Skip tour
          </button>
        </div>
      </div>
    </>
  );
}
