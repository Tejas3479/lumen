/**
 * OnboardingTour — 3-step guided tour for first-time users.
 * Shown automatically after 1.2s on first visit (localStorage gate).
 * Fully accessible: role="dialog", aria-modal, aria-live, focus management.
 */
import { useState, useEffect } from 'react';
import { X, MapPin, Camera, CheckCircle, ChevronRight, ShieldAlert, Wifi } from 'lucide-react';

interface TourStep {
  title: string;
  description: string;
  icon: React.ElementType;
  iconColor: string;
}

const TOUR_STEPS: TourStep[] = [
  {
    title: "See what's happening nearby",
    description:
      'The map shows all reported infrastructure issues in your area. Tap any marker to see details.',
    icon: MapPin,
    iconColor: 'text-blue-500',
  },
  {
    title: 'Report an issue in 60 seconds',
    description:
      'Tap the red button to report a pothole, water leak, broken light, or garbage. Add a photo for faster action.',
    icon: Camera,
    iconColor: 'text-red-500',
  },
  {
    title: 'Verify and track together',
    description:
      'Confirm issues reported by your neighbours. Watch as officials respond and track progress in real time.',
    icon: CheckCircle,
    iconColor: 'text-green-500',
  },
  {
    title: 'Offline-First Capabilities',
    description:
      'Lumen works completely offline. Drafts are securely cached in IndexedDB and sync automatically when your internet connection is restored.',
    icon: Wifi,
    iconColor: 'text-amber-500',
  },
  {
    title: 'Admin Verification & Moderation',
    description:
      'Admins can log in to moderate reports, view AI-driven triaged categories, coordinate municipal responses, and monitor real-time ward analytics.',
    icon: ShieldAlert,
    iconColor: 'text-purple-500',
  },
];

const STORAGE_KEY = 'lumen_onboarding_complete';

export default function OnboardingTour() {
  const [isVisible, setIsVisible] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    const done = localStorage.getItem(STORAGE_KEY);
    if (!done) {
      // Delay slightly so map loads first
      const timer = setTimeout(() => setIsVisible(true), 1200);
      return () => clearTimeout(timer);
    }
  }, []);

  const dismiss = () => {
    setIsVisible(false);
    localStorage.setItem(STORAGE_KEY, 'true');
  };

  const next = () => {
    if (step < TOUR_STEPS.length - 1) {
      setStep((s) => s + 1);
    } else {
      dismiss();
    }
  };

  if (!isVisible) return null;

  const current = TOUR_STEPS[step];
  const { icon: Icon } = current;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 z-50"
        onClick={dismiss}
        aria-hidden="true"
      />

      {/* Tour card */}
      <div
        className="fixed bottom-20 left-4 right-4 z-50 bg-white rounded-2xl shadow-2xl p-6"
        role="dialog"
        aria-modal="true"
        aria-label={`Onboarding tour step ${step + 1} of ${TOUR_STEPS.length}`}
        aria-live="polite"
      >
        {/* Close */}
        <button
          onClick={dismiss}
          className="absolute top-4 right-4 p-1 rounded-full hover:bg-gray-100"
          aria-label="Skip tour"
        >
          <X size={18} className="text-gray-400" aria-hidden="true" />
        </button>

        {/* Step dots */}
        <div className="flex gap-1.5 mb-4" role="group" aria-label="Tour progress">
          {TOUR_STEPS.map((_, i) => (
            <div
              key={i}
              className={`h-1.5 rounded-full transition-all ${
                i === step ? 'w-6 bg-blue-600' : 'w-1.5 bg-gray-200'
              }`}
              aria-current={i === step ? 'step' : undefined}
            />
          ))}
        </div>

        {/* Icon + Title */}
        <div className="flex items-center gap-4 mb-4">
          <div className="w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center flex-shrink-0">
            <Icon size={24} className={current.iconColor} aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-bold text-gray-900">{current.title}</h2>
          </div>
        </div>

        <p className="text-sm text-gray-600 leading-relaxed mb-5">
          {current.description}
        </p>

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <button
            onClick={dismiss}
            className="text-sm text-gray-400 hover:text-gray-600"
            aria-label="Skip the tour"
          >
            Skip tour
          </button>
          <button
            onClick={next}
            className="flex items-center gap-2 bg-blue-600 text-white text-sm font-semibold px-5 py-2.5 rounded-xl hover:bg-blue-700 transition-colors"
            aria-label={step < TOUR_STEPS.length - 1 ? 'Next step' : 'Finish tour'}
          >
            {step < TOUR_STEPS.length - 1 ? 'Next' : 'Get started'}
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </div>
      </div>
    </>
  );
}
