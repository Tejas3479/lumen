import React from 'react';
import type { IssueStatus, IssueSeverity } from '@/types';

type BadgeVariant =
  | 'default'
  | 'primary'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | IssueStatus
  | IssueSeverity;

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}

const variantClasses: Record<string, string> = {
  default:     'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  primary:     'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300',
  success:     'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  warning:     'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  danger:      'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  info:        'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  // Status variants
  reported:    'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  verified:    'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  assigned:    'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  in_progress: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  resolved:    'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  disputed:    'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  closed:      'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-400',
  // Severity variants
  low:         'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  medium:      'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  high:        'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  critical:    'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};

const dotColors: Record<string, string> = {
  default:     'bg-slate-400',
  primary:     'bg-primary-500',
  success:     'bg-emerald-500',
  warning:     'bg-amber-500',
  danger:      'bg-red-500',
  info:        'bg-blue-500',
  reported:    'bg-slate-400',
  verified:    'bg-blue-500',
  assigned:    'bg-purple-500',
  in_progress: 'bg-amber-500',
  resolved:    'bg-emerald-500',
  disputed:    'bg-orange-500',
  closed:      'bg-slate-500',
  low:         'bg-emerald-500',
  medium:      'bg-amber-500',
  high:        'bg-orange-500',
  critical:    'bg-red-500',
};

export function Badge({ variant = 'default', children, className = '', dot = false }: BadgeProps) {
  const classes = variantClasses[variant] ?? variantClasses.default;
  const dotClass = dotColors[variant] ?? dotColors.default;

  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium',
        classes,
        className,
      ].join(' ')}
    >
      {dot && (
        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotClass}`} />
      )}
      {children}
    </span>
  );
}
