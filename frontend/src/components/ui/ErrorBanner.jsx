import { AlertCircle, X } from 'lucide-react';

export const ErrorBanner = ({ message, onClose }) => (
  <div role="alert" aria-live="assertive" className="flex items-center gap-3 bg-bearish/10 text-bearish border border-bearish/20 px-4 py-3 rounded-md mb-6 animate-fade-in">
    <AlertCircle className="shrink-0" size={20} />
    <span className="flex-1 text-sm font-medium">{message}</span>
    {onClose && (
      <button 
        onClick={onClose}
        className="shrink-0 p-1 hover:bg-bearish/10 rounded-full transition-colors"
        aria-label="Close error"
      >
        <X size={16} />
      </button>
    )}
  </div>
);
