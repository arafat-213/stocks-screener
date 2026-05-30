import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';

const Select = ({
  value,
  onChange,
  options,
  placeholder = 'Select option',
  label,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  const selectedOption = options.find((opt) => opt.value === value);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (optionValue) => {
    onChange(optionValue);
    setIsOpen(false);
  };

  return (
    <div
      className={`relative w-full min-w-[160px] ${className}`}
      ref={dropdownRef}
    >
      {label && (
        <label className='block text-[10px] font-black uppercase text-slate-500 dark:text-slate-400 mb-2 tracking-[0.2em]'>
          {label}
        </label>
      )}
      <div
        className={`flex items-center justify-between px-4 py-3 bg-bg-secondary border-2 border-border rounded-xl cursor-pointer text-sm font-bold text-text transition-all duration-200 select-none hover:border-blue-500 shadow-sm ${isOpen ? 'border-blue-600 ring-4 ring-blue-500/10 shadow-lg shadow-blue-500/10' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && setIsOpen(!isOpen)}
      >
        <span className={!selectedOption ? 'text-slate-400' : ''}>
          {selectedOption
            ? selectedOption.label.toUpperCase()
            : placeholder.toUpperCase()}
        </span>
        <ChevronDown
          size={18}
          className={`text-slate-400 transition-transform duration-300 ${isOpen ? 'rotate-180 text-blue-500' : ''}`}
        />
      </div>

      {isOpen && (
        <div className='absolute top-[calc(100%+8px)] left-0 right-0 z-[1000] max-h-[300px] overflow-y-auto rounded-2xl p-2 shadow-2xl bg-bg-secondary border-2 border-border animate-fade-in'>
          {options.map((option) => (
            <div
              key={option.value}
              className={`flex items-center justify-between px-4 py-3 rounded-xl cursor-pointer text-sm font-bold transition-all duration-200 text-text hover:bg-slate-50 dark:hover:bg-slate-900/50 ${value === option.value ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400' : ''}`}
              onClick={() => handleSelect(option.value)}
            >
              <span>{option.label.toUpperCase()}</span>
              {value === option.value && (
                <Check size={16} className='text-blue-600 dark:text-blue-400' />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Select;
