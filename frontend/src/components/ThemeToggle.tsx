/**
 * ThemeToggle — Accessibility controls component.
 * Exposes high-contrast mode toggle and font-size selector.
 * Used in ProfilePage "Display Settings" section.
 */
import { Contrast } from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import type { FontSizeClass } from '@/store/appStore';

const FONT_SIZE_OPTIONS: { value: FontSizeClass; label: string; size: number; title: string }[] = [
  { value: 'text-sm',   label: 'A', size: 14, title: 'Small text'      },
  { value: 'text-base', label: 'A', size: 16, title: 'Normal text'     },
  { value: 'text-lg',   label: 'A', size: 18, title: 'Large text'      },
  { value: 'text-xl',   label: 'A', size: 20, title: 'Extra large text' },
];

export default function ThemeToggle() {
  const { isHighContrast, toggleHighContrast, fontSizeClass, setFontSize } = useAppStore();

  return (
    <div className="space-y-4" role="group" aria-label="Display settings">
      {/* ── High contrast toggle ── */}
      <div className="flex items-center justify-between">
        <div>
          <label
            htmlFor="high-contrast-toggle"
            className="text-sm font-medium text-gray-800 dark:text-slate-200 cursor-pointer"
          >
            High contrast mode
          </label>
          <p className="text-xs text-gray-500 dark:text-slate-400">
            Increases text and border contrast for better readability
          </p>
        </div>
        <button
          id="high-contrast-toggle"
          onClick={toggleHighContrast}
          role="switch"
          aria-checked={isHighContrast}
          aria-label={`High contrast mode: ${isHighContrast ? 'on' : 'off'}`}
          className={`
            relative w-11 h-6 rounded-full transition-colors flex-shrink-0
            ${isHighContrast ? 'bg-blue-600' : 'bg-gray-300 dark:bg-slate-600'}
          `}
        >
          <div
            className={`
              absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform
              ${isHighContrast ? 'translate-x-6' : 'translate-x-1'}
            `}
          />
          <Contrast
            size={10}
            className={`absolute top-1.5 right-1.5 ${isHighContrast ? 'text-white' : 'text-gray-400'}`}
            aria-hidden="true"
          />
        </button>
      </div>

      {/* ── Font size control ── */}
      <div>
        <div
          className="text-sm font-medium text-gray-800 dark:text-slate-200 mb-2"
          id="font-size-label"
        >
          Text size
        </div>
        <div
          className="flex gap-2"
          role="group"
          aria-labelledby="font-size-label"
        >
          {FONT_SIZE_OPTIONS.map(({ value, label, size, title }) => (
            <button
              key={value}
              onClick={() => setFontSize(value)}
              title={title}
              aria-pressed={fontSizeClass === value}
              aria-label={title}
              className={`
                flex-1 py-2 rounded-xl border-2 font-medium transition-all
                ${fontSizeClass === value
                  ? 'border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                  : 'border-gray-200 dark:border-slate-600 text-gray-600 dark:text-slate-400 hover:border-gray-300 dark:hover:border-slate-500'}
              `}
              style={{ fontSize: `${size}px` }}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="text-xs text-gray-400 dark:text-slate-500 mt-1.5">
          Changes text size throughout the app
        </p>
      </div>
    </div>
  );
}
