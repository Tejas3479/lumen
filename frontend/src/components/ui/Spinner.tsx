interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  label?: string;
}

const sizeClasses = {
  sm: 'h-4 w-4 border-2',
  md: 'h-6 w-6 border-2',
  lg: 'h-10 w-10 border-3',
  xl: 'h-16 w-16 border-4',
};

export function Spinner({ size = 'md', className = '', label = 'Loading...' }: SpinnerProps) {
  return (
    <div role="status" className={`inline-flex items-center justify-center ${className}`}>
      <div
        className={[
          'rounded-full border-solid border-primary-200 dark:border-primary-900',
          'border-t-primary-600 dark:border-t-primary-400',
          'animate-spin',
          sizeClasses[size],
        ].join(' ')}
      />
      <span className="sr-only">{label}</span>
    </div>
  );
}

interface PageSpinnerProps {
  label?: string;
}

export function PageSpinner({ label = 'Loading...' }: PageSpinnerProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[200px] gap-3">
      <Spinner size="lg" />
      <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
    </div>
  );
}
