import { X, Shield, Bot, Wifi, CheckCircle, Key } from 'lucide-react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export default function AboutDemoModal({ isOpen, onClose }: Props) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="About this demo"
    >
      <div
        className="relative w-full max-w-lg bg-white dark:bg-slate-900 rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        style={{ animation: 'slideUp 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100 dark:border-slate-800">
          <div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <span>Lumen Demo Guide</span>
              <span className="text-xs bg-blue-100 text-blue-800 px-2.5 py-0.5 rounded-full font-medium">
                Hackathon Edition
              </span>
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Evaluating Lumen in under 60 seconds
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-slate-850 text-gray-400 dark:text-gray-500 hover:text-gray-650"
            aria-label="Close details"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5 text-sm text-gray-600 dark:text-gray-300">
          
          {/* Quick-Start credentials */}
          <div className="bg-slate-50 dark:bg-slate-800/50 rounded-2xl p-4 border border-slate-100 dark:border-slate-800/80">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2.5 flex items-center gap-1.5">
              <Key size={14} className="text-blue-500" />
              Demo Accounts & Logins
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="p-2.5 bg-white dark:bg-slate-800 rounded-xl border border-slate-200/50 dark:border-slate-700">
                <span className="font-bold text-gray-700 dark:text-gray-200 block mb-0.5">🛡️ Admin Dashboard</span>
                <span className="text-slate-500 block">admin@lumen.civic</span>
                <span className="text-slate-400">Password: admin123</span>
              </div>
              <div className="p-2.5 bg-white dark:bg-slate-800 rounded-xl border border-slate-200/50 dark:border-slate-700">
                <span className="font-bold text-gray-700 dark:text-gray-200 block mb-0.5">👤 Citizen view</span>
                <span className="text-slate-500 block">priya@example.com</span>
                <span className="text-slate-400">Password: citizen123</span>
              </div>
            </div>
          </div>

          {/* Demo walkthrough */}
          <div className="bg-blue-50/50 dark:bg-blue-950/20 rounded-2xl p-4 border border-blue-100/50 dark:border-blue-900/30">
            <h3 className="text-xs font-bold uppercase tracking-wider text-blue-700 dark:text-blue-400 mb-2.5 flex items-center gap-1.5">
              <span>📋 Step-by-Step Demo Walkthrough</span>
            </h3>
            <ol className="list-decimal list-inside space-y-2 text-xs text-gray-600 dark:text-gray-300">
              <li className="leading-relaxed">
                <strong className="text-gray-800 dark:text-white">Report:</strong> Click the red <span className="bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 px-1.5 py-0.5 rounded font-bold font-mono">+</span> button, describe a civic issue (e.g. "Pothole on Residency Rd"), and submit. Watch Gemini categorize it instantly!
              </li>
              <li className="leading-relaxed">
                <strong className="text-gray-800 dark:text-white">Verify:</strong> Log in as <span className="font-mono text-slate-500 dark:text-slate-400">priya@example.com</span>, select the pin on the map, and click <span className="font-semibold text-slate-700 dark:text-slate-200">Verify</span> to add community trust.
              </li>
              <li className="leading-relaxed">
                <strong className="text-gray-800 dark:text-white">Resolve:</strong> Log in as <span className="font-mono text-slate-500 dark:text-slate-400">admin@lumen.civic</span>, go to the Admin Dashboard (link in bottom nav), assign the issue to a ward team, and resolve it.
              </li>
            </ol>
          </div>

          {/* AI Agents architecture */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
              <Bot size={14} className="text-purple-500" />
              Autonomous AI Agents (Google Gemini)
            </h3>
            
            <div className="space-y-2.5">
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-purple-50 dark:bg-purple-950/30 flex items-center justify-center flex-shrink-0">
                  <Bot size={16} className="text-purple-600 dark:text-purple-400" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-gray-800 dark:text-white">Triage Agent</h4>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">
                    Uses Gemini function calling to read live ward context, suggesting category, severity, and official department for every incoming issue.
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-purple-50 dark:bg-purple-950/30 flex items-center justify-center flex-shrink-0">
                  <Shield size={16} className="text-purple-600 dark:text-purple-400" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-gray-800 dark:text-white">Escalation Agent</h4>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">
                    Runs autonomously every 30 minutes to detect issues violating SLA times and automatically escalates their priority.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Key Features */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
              <CheckCircle size={14} className="text-green-500" />
              Core Product Pillars
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="flex gap-2">
                <Wifi className="text-amber-500 flex-shrink-0 mt-0.5" size={14} />
                <div>
                  <span className="font-semibold block text-slate-700 dark:text-slate-200">Offline-first Sync</span>
                  <span className="text-slate-400">Stores reports in IndexedDB and uploads automatically when internet is back.</span>
                </div>
              </div>
              <div className="flex gap-2">
                <CheckCircle className="text-green-500 flex-shrink-0 mt-0.5" size={14} />
                <div>
                  <span className="font-semibold block text-slate-700 dark:text-slate-200">GPS Verification</span>
                  <span className="text-slate-400">Citizens verify issues using GPS geofencing or soft knowledge checks.</span>
                </div>
              </div>
            </div>
          </div>

        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-slate-50 dark:bg-slate-900 border-t border-gray-100 dark:border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs transition-colors"
          >
            Got it, let's explore!
          </button>
        </div>
      </div>

      <style>{`
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(30px) scale(0.98); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </div>
  );
}
