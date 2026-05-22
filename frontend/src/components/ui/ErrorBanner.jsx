import { AlertCircle, X } from 'lucide-react';

export const ErrorBanner = ({ message, onClose }) => (
  <div role="alert" aria-live="assertive" className="flex items-center gap-4 bg-red-500/10 text-red-600 dark:text-red-400 border-2 border-red-500/20 px-5 py-4 rounded-2xl mb-8 animate-fade-in shadow-sm">
    <AlertCircle className="shrink-0" size={24} />
    <span className="flex-1 text-sm font-black uppercase tracking-tight leading-relaxed">{message}</span>
    {onClose && (
      <button 
        onClick={onClose}
        className="shrink-0 p-2 hover:bg-red-500/10 rounded-full transition-all active:scale-90 border-none bg-transparent cursor-pointer"
        aria-label="Close error"
      >
        <X size={20} className="text-red-500" />
      </button>
    )}
  </div>
);
