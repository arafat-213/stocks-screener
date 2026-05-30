import { useEffect } from 'react';
import { X } from 'lucide-react';

const BottomSheet = ({ isOpen, onClose, title, children }) => {
  // Prevent scrolling when the sheet is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className='fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4'>
      {/* Backdrop */}
      <div
        className='absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-fade-in'
        onClick={onClose}
      />

      {/* Sheet Content */}
      <div
        className={`relative w-full max-w-lg bg-white dark:bg-slate-900 rounded-t-3xl sm:rounded-3xl shadow-2xl border-t sm:border-2 border-border
        max-h-[85vh] overflow-hidden flex flex-col
        animate-slide-up sm:animate-zoom-in`}
      >
        {/* Drag Handle for mobile */}
        <div className='sm:hidden w-full flex justify-center p-3'>
          <div className='w-12 h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full' />
        </div>

        {/* Header */}
        <div className='px-6 py-4 border-b border-border flex justify-between items-center'>
          <h3 className='text-lg font-black uppercase tracking-tight'>
            {title}
          </h3>
          <button
            onClick={onClose}
            className='p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors'
          >
            <X size={20} className='text-slate-500' />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className='flex-1 overflow-y-auto p-6 pt-2 pb-10 sm:pb-6'>
          {children}
        </div>
      </div>
    </div>
  );
};

export default BottomSheet;
