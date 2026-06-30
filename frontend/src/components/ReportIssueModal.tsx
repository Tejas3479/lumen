/**
 * ReportIssueModal — 3-step guided report wizard.
 *
 * Step 1: Choose category
 * Step 2: Describe (title + description + emergency flag + anonymous toggle)
 * Step 3: Add media + confirm location
 *
 * Submits via FormData (multipart) to POST /issues.
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import {
  X, ChevronRight, ChevronLeft, Camera, AlertTriangle,
  MapPin, Check, Trash2, Mic, MicOff,
} from 'lucide-react';
import api from '@/lib/api';
import { useIssueStore } from '@/store/issueStore';
import { useGeolocation } from '@/hooks/useGeolocation';
import { useUserStore } from '@/store/userStore';
import { useIssuesApi } from '@/hooks/useApi';
import { useOfflineQueue } from '@/hooks/useOfflineQueue';
import type { Category, ReportFormDraft, Issue } from '@/types';
import toast from 'react-hot-toast';

// ── Types ─────────────────────────────────────────────────────

interface DuplicateCandidate {
  issue_id: string;
  title: string;
  status: string;
  address: string | null;
  vote_count: number;
  verification_count: number;
  category: string | null;
  distance_meters: number;
  similarity_score: number;
  duplicate_strength: 'possible' | 'likely';
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  categories: Category[];
}

const CATEGORY_EMOJI: Record<string, string> = {
  pothole:       '🕳️',
  water_leakage: '💧',
  streetlight:   '💡',
  garbage:       '🗑️',
  drainage:      '🌊',
  road_damage:   '🚧',
  tree_hazard:   '🌳',
  vandalism:     '✏️',
  noise:         '🔊',
  other:         '⚠️',
};

const SEVERITY_OPTIONS = [
  { value: 'low',      label: 'Low',      color: '#10b981', desc: 'Not urgent' },
  { value: 'medium',   label: 'Medium',   color: '#f59e0b', desc: 'Needs attention' },
  { value: 'high',     label: 'High',     color: '#f97316', desc: 'Affects daily life' },
  { value: 'critical', label: 'Critical', color: '#ef4444', desc: 'Dangerous' },
];

const MAX_FILES = 3;
const MAX_TITLE = 120;
const MAX_DESC = 2000;

function generateDraftId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `draft_${crypto.randomUUID()}`;
  }
  return `draft_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}


export default function ReportIssueModal({ isOpen, onClose, categories }: Props) {
  const { location } = useGeolocation();
  const isAuthenticated = useUserStore((s) => s.isAuthenticated);
  const { supportIssue } = useIssuesApi();
  const { saveDraft, requestBackgroundSync } = useOfflineQueue();

  // ── Speech Recognition State ────────────────────────────────
  const [isListening, setIsListening] = useState(false);
  const speechSupported = typeof window !== 'undefined' && 
    Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    if (!speechSupported) return;
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = false;
    rec.lang = 'en-IN'; // Indian English as specified in mandate

    rec.onresult = (event: any) => {
      const lastIndex = event.results.length - 1;
      const transcript = event.results[lastIndex][0].transcript;
      setDraft((d) => ({
        ...d,
        description: d.description + (d.description ? ' ' : '') + transcript.trim(),
      }));
    };

    rec.onerror = (event: any) => {
      if (event.error !== 'aborted') {
        console.error('Speech recognition error:', event.error);
        toast.error('Voice input error. Please type your description.');
      }
      setIsListening(false);
    };

    rec.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = rec;

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }
    };
  }, [speechSupported]);

  const toggleListening = useCallback(() => {
    if (!recognitionRef.current) return;
    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
        toast.success('Listening… speak now 🎙️', { id: 'listening-toast' });
      } catch (err) {
        // Recognition already started or error
      }
    }
  }, [isListening]);

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // ── Duplicate detection state ──────────────────────────────
  const [duplicates, setDuplicates] = useState<DuplicateCandidate[]>([]);
  const [duplicateChecked, setDuplicateChecked] = useState(false);
  const [showDuplicates, setShowDuplicates] = useState(false);
  const [isDuplicateChecking, setIsDuplicateChecking] = useState(false);

  const [draft, setDraft] = useState<ReportFormDraft>({
    step: 1,
    category_id: null,
    category_name: null,
    title: '',
    description: '',
    is_emergency: false,
    is_anonymous: false,
    media_files: [],
    latitude: null,
    longitude: null,
    address: '',
    idempotency_key: generateDraftId(),
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [mediaPreviews, setMediaPreviews] = useState<string[]>([]);
  const addressInputRef = useRef<HTMLInputElement>(null);

  const updateDraft = useCallback((fields: Partial<ReportFormDraft>) => {
    setDraft((d) => ({ ...d, ...fields }));
  }, []);

  // Initialize Google Places Autocomplete if available
  useEffect(() => {
    const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
    if (!apiKey || !addressInputRef.current || step !== 3) return;

    let autocomplete: any = null;

    const initAutocomplete = async () => {
      try {
        const { Loader } = await import('@googlemaps/js-api-loader');
        const loader = new Loader({ apiKey, version: 'weekly', libraries: ['places'], language: 'kn' });
        const google = await loader.load();

        autocomplete = new google.maps.places.Autocomplete(
          addressInputRef.current!,
          {
            types: ['establishment', 'geocode'],
            componentRestrictions: { country: 'in' },  // India only
            fields: ['formatted_address', 'geometry', 'name'],
          }
        );

        autocomplete.addListener('place_changed', () => {
          const place = autocomplete.getPlace();
          if (place.geometry?.location) {
            updateDraft({
              address: place.formatted_address || place.name || '',
              latitude: place.geometry.location.lat(),
              longitude: place.geometry.location.lng(),
            });
          }
        });
      } catch {
        // Places API unavailable — use plain text input
      }
    };

    initAutocomplete();
  }, [step, updateDraft]);

  // Sync location into draft
  useEffect(() => {
    if (location?.latitude && !draft.latitude) {
      setDraft((d) => ({
        ...d,
        latitude: location.latitude,
        longitude: location.longitude,
      }));
    }
  }, [location?.latitude, location?.longitude, draft.latitude]);

  // Reset on open
  useEffect(() => {
    if (isOpen) {
      setStep(1);
      setSubmitError(null);
      setDraft({
        step: 1,
        category_id: null,
        category_name: null,
        title: '',
        description: '',
        is_emergency: false,
        is_anonymous: false,
        media_files: [],
        latitude: location?.latitude ?? null,
        longitude: location?.longitude ?? null,
        address: '',
        idempotency_key: generateDraftId(),
      });
      setMediaPreviews([]);
    } else {
      if (recognitionRef.current && isListening) {
        recognitionRef.current.stop();
        setIsListening(false);
      }
    }
  }, [isOpen, isListening]);

  // Lock body scroll when open
  useEffect(() => {
    document.body.style.overflow = isOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [isOpen]);

  // Reset duplicate state when modal opens so each new report starts fresh
  useEffect(() => {
    if (isOpen) {
      setDuplicates([]);
      setDuplicateChecked(false);
      setShowDuplicates(false);
    }
  }, [isOpen]);

  // ── Duplicate check — triggered when Step 3 is reached ────
  const checkForDuplicates = useCallback(async () => {
    if (!draft.latitude || !draft.longitude) return;
    if (!draft.description || draft.description.trim().length < 10) return;

    const titleForCheck =
      draft.title.trim().length >= 5
        ? draft.title.trim()
        : draft.description.trim().slice(0, 60);

    setIsDuplicateChecking(true);
    try {
      const response = await api.post<{
        has_duplicates: boolean;
        duplicates: DuplicateCandidate[];
      }>('/issues/check-duplicates', {
        title: titleForCheck,
        description: draft.description.trim(),
        latitude: draft.latitude,
        longitude: draft.longitude,
        category_id: draft.category_id || undefined,
      });

      const data = response.data;
      setDuplicates(data.duplicates);
      setDuplicateChecked(true);
      setShowDuplicates(data.has_duplicates);
    } catch {
      // Duplicate check failure must NEVER block submission
      setDuplicateChecked(true);
      setShowDuplicates(false);
    } finally {
      setIsDuplicateChecking(false);
    }
  }, [draft.latitude, draft.longitude, draft.title, draft.description, draft.category_id]);

  // Trigger duplicate check automatically when user reaches Step 3
  useEffect(() => {
    if (step === 3 && !duplicateChecked) {
      checkForDuplicates();
    }
  }, [step, duplicateChecked, checkForDuplicates]);

  const selectCategory = useCallback((cat: Category) => {
    setDraft((d) => ({ ...d, category_id: cat.id, category_name: cat.name }));
    setStep(2);
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;

    const remaining = MAX_FILES - draft.media_files.length;
    const newFiles = files.slice(0, remaining);

    setDraft((d) => ({ ...d, media_files: [...d.media_files, ...newFiles] }));

    newFiles.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (ev) => {
        setMediaPreviews((p) => [...p, ev.target?.result as string]);
      };
      reader.readAsDataURL(file);
    });
  };

  const removeFile = (index: number) => {
    setDraft((d) => ({
      ...d,
      media_files: d.media_files.filter((_, i) => i !== index),
    }));
    setMediaPreviews((p) => p.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    if (!draft.latitude || !draft.longitude) {
      setSubmitError('Location is required. Please enable location access.');
      return;
    }
    if (!draft.title.trim() || draft.title.trim().length < 5) {
      setSubmitError('Title must be at least 5 characters.');
      return;
    }
    if (!draft.description.trim() || draft.description.trim().length < 10) {
      setSubmitError('Description must be at least 10 characters.');
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);
    setUploadProgress(0);

    const formData = new FormData();
    formData.append('title', draft.title.trim());
    formData.append('description', draft.description.trim());
    formData.append('latitude', String(draft.latitude));
    formData.append('longitude', String(draft.longitude));
    if (draft.address) formData.append('address', draft.address);
    formData.append('severity', 'medium');
    formData.append('is_anonymous', String(draft.is_anonymous));
    formData.append('is_emergency', String(draft.is_emergency));
    if (draft.category_id) formData.append('category_id', draft.category_id);
    formData.append('offline_draft_id', draft.idempotency_key);
    draft.media_files.forEach((file) => formData.append('files', file));

    try {
      const response = await api.post<Issue>('/issues', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const pct = Math.round(
              (progressEvent.loaded / progressEvent.total) * 100
            );
            setUploadProgress(pct);
          }
        },
      });

      const addIssue = useIssueStore.getState().addIssue;
      addIssue(response.data);
      toast.success('Report submitted! Your issue is now live on the map. 📍');
      setIsSubmitting(false);
      setIsSuccess(true);
      setTimeout(() => {
        setIsSuccess(false);
        onClose();
      }, 2500);
    } catch (err: any) {
      setIsSubmitting(false);

      // Offline or network error → queue for background sync
      if (!navigator.onLine || err?.code === 'ERR_NETWORK' || err?.message === 'Network Error') {
        await saveDraft(draft);
        await requestBackgroundSync();
        toast.success('Saved! Will upload when you\'re back online. 📶');
        onClose();
        return;
      }

      const msg =
        err?.response?.data?.detail?.message ||
        err?.response?.data?.message ||
        err?.message ||
        'Failed to submit report. Please try again.';
      toast.error(msg);
      setSubmitError(msg);
    }
  };

  const canGoNext = () => {
    if (step === 1) return Boolean(draft.category_id);
    if (step === 2) return draft.title.trim().length >= 5 && draft.description.trim().length >= 10;
    return true;
  };

  if (!isOpen) return null;

  const selectedEmoji = draft.category_name
    ? (CATEGORY_EMOJI[draft.category_name] ?? '⚠️')
    : '📋';

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-label="Report an issue"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal panel */}
      <div className="relative w-full sm:max-w-lg sm:mx-4 bg-white dark:bg-slate-900 rounded-t-3xl sm:rounded-3xl shadow-2xl flex flex-col max-h-[92vh]"
           style={{ animation: 'slideUp 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)' }}>

        {isSuccess ? (
          <div
            className="flex flex-col items-center justify-center py-12 px-6 text-center"
            role="status"
            aria-live="assertive"
            aria-label="Report submitted successfully"
          >
            {/* Animated checkmark */}
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4">
              <svg viewBox="0 0 24 24" className="w-10 h-10 text-green-500" fill="none">
                <circle cx="12" cy="12" r="11" stroke="currentColor" strokeWidth="2" />
                <path
                  d="M7 12l3.5 3.5 6.5-7"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="animate-dash"
                />
              </svg>
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-1">Report is live! ✓</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
              Your issue is now on the community map.
            </p>
            <p className="text-xs text-blue-600 dark:text-blue-400 animate-pulse">
              🤖 Google Gemini is analysing your photo…
            </p>
          </div>
        ) : (
          <>
            {/* Progress bar */}
            <div className="h-1 bg-slate-100 dark:bg-slate-800 rounded-t-3xl sm:rounded-t-3xl overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-primary-500 to-violet-500 transition-all duration-500"
            style={{ width: `${(step / 3) * 100}%` }}
          />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            {step > 1 && (
              <button
                onClick={() => setStep((s) => (s - 1) as 1 | 2 | 3)}
                className="p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                aria-label="Go back"
              >
                <ChevronLeft size={18} className="text-slate-400" />
              </button>
            )}
            <div>
              <h2 className="font-bold text-slate-900 dark:text-white text-base">
                {step === 1 && 'What type of issue?'}
                {step === 2 && 'Describe the issue'}
                {step === 3 && 'Add media & confirm'}
              </h2>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                Step {step} of 3
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            aria-label="Close"
          >
            <X size={18} className="text-slate-400" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 pb-3">

          {/* ── STEP 1: Category picker ── */}
          {step === 1 && (
            <div className="grid grid-cols-2 gap-3 pb-4">
              {categories.length > 0 ? categories.map((cat) => {
                const emoji = CATEGORY_EMOJI[cat.name] ?? '⚠️';
                const isSelected = draft.category_id === cat.id;
                return (
                  <button
                    key={cat.id}
                    onClick={() => selectCategory(cat)}
                    className={`p-4 rounded-2xl border-2 transition-all duration-200 text-left hover:scale-[1.02] active:scale-[0.98] ${
                      isSelected
                        ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30'
                        : 'border-slate-200 dark:border-slate-700 hover:border-primary-300 dark:hover:border-primary-600 bg-white dark:bg-slate-800'
                    }`}
                  >
                    <span className="text-2xl block mb-2">{emoji}</span>
                    <p className="font-semibold text-sm text-slate-900 dark:text-white leading-tight">
                      {cat.display_name}
                    </p>
                    {cat.avg_resolution_days > 0 && (
                      <p className="text-[10px] text-slate-400 mt-1">
                        ~{cat.avg_resolution_days}d avg resolution
                      </p>
                    )}
                  </button>
                );
              }) : (
                // Fallback static categories when API not loaded yet
                [
                  { id: 'pothole', name: 'pothole', display_name: 'Pothole' },
                  { id: 'water', name: 'water_leakage', display_name: 'Water Leakage' },
                  { id: 'light', name: 'streetlight', display_name: 'Streetlight' },
                  { id: 'garbage', name: 'garbage', display_name: 'Garbage' },
                  { id: 'drain', name: 'drainage', display_name: 'Drainage' },
                  { id: 'other', name: 'other', display_name: 'Other' },
                ].map((cat) => (
                  <button
                    key={cat.id}
                    onClick={() => setDraft((d) => ({ ...d, category_id: cat.id, category_name: cat.name }))}
                    className="p-4 rounded-2xl border-2 border-slate-200 dark:border-slate-700 hover:border-primary-300 bg-white dark:bg-slate-800 text-left transition-all duration-200 hover:scale-[1.02]"
                  >
                    <span className="text-2xl block mb-2">{CATEGORY_EMOJI[cat.name] ?? '⚠️'}</span>
                    <p className="font-semibold text-sm text-slate-900 dark:text-white">
                      {cat.display_name}
                    </p>
                  </button>
                ))
              )}
            </div>
          )}

          {/* ── STEP 2: Describe ── */}
          {step === 2 && (
            <div className="space-y-4 pb-4">
              {/* Title */}
              <div>
                <label className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                  Title *
                </label>
                <input
                  id="report-title"
                  type="text"
                  placeholder="Short, clear title (e.g. 'Deep pothole on Main St')"
                  maxLength={MAX_TITLE}
                  value={draft.title}
                  onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
                  className="mt-1.5 w-full input"
                  autoFocus
                />
                <p className="text-right text-[10px] text-slate-400 mt-1">
                  {draft.title.length}/{MAX_TITLE}
                </p>
              </div>

              {/* Description */}
              <div>
                <div className="flex justify-between items-center">
                  <label className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                    Description *
                  </label>
                  {speechSupported ? (
                    <button
                      type="button"
                      onClick={toggleListening}
                      className={`flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full transition-all ${
                        isListening
                          ? 'bg-red-500 text-white animate-pulse'
                          : 'bg-slate-100 hover:bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                      }`}
                      aria-label={isListening ? "Stop listening" : "Start voice input"}
                    >
                      {isListening ? (
                        <>
                          <MicOff size={10} />
                          <span>Listening…</span>
                        </>
                      ) : (
                        <>
                          <Mic size={10} />
                          <span>Voice input</span>
                        </>
                      )}
                    </button>
                  ) : (
                    <span className="text-[9px] text-slate-400" title="Voice input is not supported in this browser. Please type.">
                      Voice unsupported
                    </span>
                  )}
                </div>
                <textarea
                  id="report-description"
                  placeholder="Describe the issue: location details, how long it's been there, who it affects..."
                  maxLength={MAX_DESC}
                  value={draft.description}
                  onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
                  rows={4}
                  className="mt-1.5 w-full input resize-none"
                />
                <p className="text-right text-[10px] text-slate-400 mt-1">
                  {draft.description.length}/{MAX_DESC}
                </p>
              </div>

              {/* Emergency toggle */}
              <div
                className={`flex items-center justify-between p-3.5 rounded-2xl cursor-pointer transition-colors ${
                  draft.is_emergency
                    ? 'bg-red-50 dark:bg-red-900/20 border-2 border-red-400'
                    : 'bg-slate-50 dark:bg-slate-800 border-2 border-transparent hover:border-red-200'
                }`}
                onClick={() => setDraft((d) => ({ ...d, is_emergency: !d.is_emergency }))}
              >
                <div className="flex items-center gap-3">
                  <AlertTriangle
                    size={18}
                    className={draft.is_emergency ? 'text-red-500' : 'text-slate-400'}
                  />
                  <div>
                    <p className={`font-semibold text-sm ${draft.is_emergency ? 'text-red-600 dark:text-red-400' : 'text-slate-700 dark:text-slate-300'}`}>
                      Emergency Issue
                    </p>
                    <p className="text-[10px] text-slate-400">
                      Dangerous or requires immediate action
                    </p>
                  </div>
                </div>
                <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
                  draft.is_emergency ? 'border-red-500 bg-red-500' : 'border-slate-300'
                }`}>
                  {draft.is_emergency && <Check size={12} className="text-white" />}
                </div>
              </div>

              {/* Anonymous toggle */}
              {isAuthenticated && (
                <div
                  className="flex items-center justify-between p-3.5 rounded-2xl cursor-pointer bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                  onClick={() => setDraft((d) => ({ ...d, is_anonymous: !d.is_anonymous }))}
                >
                  <div>
                    <p className="font-semibold text-sm text-slate-700 dark:text-slate-300">
                      Report Anonymously
                    </p>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      Your name won't appear on the public map
                    </p>
                  </div>
                  <div className={`w-10 h-6 rounded-full transition-colors relative ${
                    draft.is_anonymous ? 'bg-primary-500' : 'bg-slate-300 dark:bg-slate-600'
                  }`}>
                    <div className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                      draft.is_anonymous ? 'left-5' : 'left-1'
                    }`} />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── STEP 3: Media + Location ── */}
          {step === 3 && (
            <div className="space-y-4 pb-4">

              {/* ── Duplicate Suggestion Panel ── */}
              {isDuplicateChecking && (
                <div
                  className="bg-amber-50 border border-amber-100 rounded-xl p-3 flex items-center gap-2 text-xs text-amber-700"
                  role="status"
                  aria-live="polite"
                >
                  <span className="w-4 h-4 border-2 border-amber-400/30 border-t-amber-500 rounded-full animate-spin flex-shrink-0" aria-hidden="true" />
                  Checking for similar reports nearby…
                </div>
              )}

              {!isDuplicateChecking && showDuplicates && duplicates.length > 0 && (
                <div
                  className="bg-amber-50 border border-amber-200 rounded-xl p-3 space-y-3"
                  role="alert"
                  aria-live="polite"
                  aria-label="Similar issues found nearby"
                >
                  {/* Panel header */}
                  <div className="flex items-start gap-2">
                    <span className="text-amber-600 text-lg flex-shrink-0" aria-hidden="true">⚠️</span>
                    <div>
                      <div className="text-sm font-semibold text-amber-800">
                        Similar issue{duplicates.length > 1 ? 's' : ''} already reported nearby
                      </div>
                      <div className="text-xs text-amber-600 mt-0.5">
                        Supporting an existing report is more powerful than filing a new one.
                      </div>
                    </div>
                  </div>

                  {/* Candidate cards */}
                  {duplicates.map((dup) => (
                    <div
                      key={dup.issue_id}
                      className="bg-white rounded-lg p-3 border border-amber-100 space-y-2"
                    >
                      <div className="text-xs font-medium text-gray-800 line-clamp-2">
                        {dup.title}
                      </div>
                      <div className="flex items-center flex-wrap gap-2 text-xs text-gray-500">
                        <span>{Math.round(dup.distance_meters)}m away</span>
                        <span aria-hidden="true">·</span>
                        <span>{dup.vote_count} supporting</span>
                        {dup.category && (
                          <>
                            <span aria-hidden="true">·</span>
                            <span>{dup.category}</span>
                          </>
                        )}
                        <span aria-hidden="true">·</span>
                        <span
                          className={`font-semibold ${
                            dup.duplicate_strength === 'likely'
                              ? 'text-red-600'
                              : 'text-amber-600'
                          }`}
                        >
                          {dup.duplicate_strength === 'likely'
                            ? '🔴 Likely same issue'
                            : '🟡 Possibly same issue'}
                        </span>
                      </div>
                      <button
                        onClick={async () => {
                          await supportIssue(dup.issue_id);
                          onClose();
                        }}
                        className="w-full text-xs bg-amber-500 text-white py-2 rounded-lg font-semibold hover:bg-amber-600 active:bg-amber-700 transition-colors"
                        aria-label={`Support existing issue: ${dup.title}`}
                      >
                        ✓ Add my support to this existing report
                      </button>
                    </div>
                  ))}

                  {/* Dismiss — submit new report anyway */}
                  <button
                    onClick={() => setShowDuplicates(false)}
                    className="w-full text-xs text-amber-700 hover:text-amber-900 underline py-1 transition-colors"
                    aria-label="Dismiss duplicate warning and submit new report"
                  >
                    No, this is a different issue — submit mine
                  </button>
                </div>
              )}
              {/* Media upload */}
              <div>
                <label className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                  Photos / Videos (optional, max {MAX_FILES})
                </label>
                <p className="text-[10px] text-slate-400 mt-0.5 mb-3">
                  Photos of the issue help officials prioritise and verify faster
                </p>

                {/* Previews */}
                {mediaPreviews.length > 0 && (
                  <div className="flex gap-2 flex-wrap mb-3">
                    {mediaPreviews.map((src, i) => (
                      <div key={i} className="relative w-20 h-20 rounded-xl overflow-hidden bg-slate-100 dark:bg-slate-800 group">
                        <img src={src} alt={`Upload ${i + 1}`} className="w-full h-full object-cover" />
                        <button
                          onClick={() => removeFile(i)}
                          className="absolute top-1 right-1 p-1 rounded-lg bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                          aria-label="Remove"
                        >
                          <Trash2 size={10} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {draft.media_files.length < MAX_FILES && (
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full h-20 border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-2xl flex items-center justify-center gap-3 text-slate-400 hover:border-primary-400 hover:text-primary-500 transition-colors"
                  >
                    <Camera size={20} />
                    <span className="text-sm font-medium">Add Photo or Video</span>
                  </button>
                )}

                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime"
                  multiple
                  className="hidden"
                  onChange={handleFileChange}
                />
              </div>

              {/* Location display */}
              <div className="p-3.5 rounded-2xl bg-slate-50 dark:bg-slate-800">
                <div className="flex items-center gap-2 mb-2">
                  <MapPin size={14} className="text-primary-500 flex-shrink-0" />
                  <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                    Location
                  </span>
                </div>
                <div className="space-y-2">
                  <input
                    ref={addressInputRef}
                    id="report-address"
                    type="text"
                    value={draft.address}
                    onChange={(e) => updateDraft({ address: e.target.value })}
                    placeholder="e.g. Near Koramangala water tank, 6th Block"
                    className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-slate-700 dark:border-slate-600 dark:text-white"
                    aria-describedby="address-hint"
                  />
                  <p id="address-hint" className="text-xs text-gray-400 mt-1">
                    {import.meta.env.VITE_GOOGLE_MAPS_API_KEY
                      ? 'Start typing for address suggestions'
                      : 'Type the nearest landmark or street name'}
                  </p>
                  {draft.latitude ? (
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      {draft.latitude.toFixed(5)}°, {draft.longitude?.toFixed(5)}°
                    </p>
                  ) : (
                    <p className="text-sm text-slate-400">
                      Waiting for GPS location...
                    </p>
                  )}
                </div>
              </div>

              {/* Summary */}
              <div className="p-3.5 rounded-2xl bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800">
                <p className="text-xs font-semibold text-primary-700 dark:text-primary-300 mb-2">
                  Your report summary
                </p>
                <p className="text-sm font-bold text-slate-900 dark:text-white">
                  {selectedEmoji} {draft.title}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">
                  {draft.description}
                </p>
                <div className="flex items-center gap-2 mt-2">
                  {draft.is_emergency && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400 rounded-md font-semibold">
                      🚨 Emergency
                    </span>
                  )}
                  {draft.is_anonymous && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 text-slate-500 rounded-md">
                      Anonymous
                    </span>
                  )}
                  {draft.media_files.length > 0 && (
                    <span className="text-[10px] text-slate-400">
                      📎 {draft.media_files.length} file{draft.media_files.length > 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              </div>

              {/* Error */}
              {submitError && (
                <div className="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
                  <p className="text-sm text-red-600 dark:text-red-400">{submitError}</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer — nav buttons */}
        <div className="px-5 py-4 border-t border-slate-100 dark:border-slate-800">
          {/* Upload progress bar — shown while submitting on step 3 */}
          {step === 3 && isSubmitting && (
            <div className="mb-3 space-y-1" aria-live="polite" aria-label="Upload progress">
              <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
                <span>Uploading your report…</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-primary-500 to-violet-500 rounded-full transition-all duration-300 ease-out"
                  style={{ width: `${uploadProgress}%` }}
                  role="progressbar"
                  aria-valuenow={uploadProgress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
              </div>
            </div>
          )}

          {step < 3 ? (
            <button
              id="report-modal-next"
              onClick={() => {
                if (step === 1 && !draft.category_id) return;
                setStep((s) => (s + 1) as 1 | 2 | 3);
              }}
              disabled={!canGoNext()}
              className="w-full btn btn-primary py-3.5 text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {step === 1 ? 'Describe the issue' : 'Add media & review'}
              <ChevronRight size={16} />
            </button>
          ) : (
            <button
              id="report-modal-submit"
              onClick={handleSubmit}
              disabled={isSubmitting || !draft.latitude}
              className="w-full btn btn-primary py-3.5 text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Submitting...
                </>
              ) : (
                <>
                  <Check size={16} />
                  Submit Report
                </>
              )}
            </button>
          )}

          {step === 3 && (
            <p className="text-center text-[10px] text-slate-400 dark:text-slate-500 mt-2">
              Your report will be reviewed and verified by the community
            </p>
          )}
        </div>
        </>
        )}
      </div>

      <style>{`
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(40px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
        .input {
          width: 100%;
          padding: 0.625rem 0.875rem;
          border-radius: 0.875rem;
          border: 1.5px solid #e2e8f0;
          background: white;
          font-size: 0.875rem;
          outline: none;
          transition: border-color 0.15s;
        }
        .dark .input {
          background: #1e293b;
          border-color: #334155;
          color: white;
        }
        .input:focus {
          border-color: #6366f1;
          box-shadow: 0 0 0 3px rgba(99,102,241,0.1);
        }
      `}</style>
    </div>
  );
}
