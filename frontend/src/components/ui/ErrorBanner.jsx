import { AlertCircle, X } from 'lucide-react';

export const ErrorBanner = ({ message, onClose }) => (
  <div role="alert" aria-live="assertive" className="error-banner">
    <AlertCircle size={20} />
    <span>{message}</span>
    {onClose && <button onClick={onClose}><X size={16} /></button>}
  </div>
);
