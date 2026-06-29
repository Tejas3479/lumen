import { Link } from 'react-router-dom';
import { MapPin, Home } from 'lucide-react';

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 text-center">
      <div className="w-20 h-20 bg-slate-100 dark:bg-slate-800 rounded-3xl flex items-center justify-center mx-auto mb-6">
        <MapPin className="text-slate-400" size={36} />
      </div>
      <h1 className="text-4xl font-bold text-slate-900 dark:text-white mb-2">404</h1>
      <p className="text-xl font-semibold text-slate-700 dark:text-slate-300 mb-2">Page not found</p>
      <p className="text-slate-500 dark:text-slate-400 max-w-sm mb-8">
        This page doesn't exist. Maybe the issue was already resolved?
      </p>
      <Link
        to="/"
        className="inline-flex items-center gap-2 btn-primary"
      >
        <Home size={16} />
        Back to Home
      </Link>
    </div>
  );
}
