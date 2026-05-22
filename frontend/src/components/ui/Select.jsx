import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';

const Select = ({ value, onChange, options, placeholder = "Select option", label, className = "" }) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  const selectedOption = options.find(opt => opt.value === value);

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
    <div className={`relative w-full min-w-[160px] ${className}`} ref={dropdownRef}>
      {label && <label className="block text-[0.75rem] font-bold uppercase text-text-muted mb-2 tracking-wider">{label}</label>}
      <div 
        className={`flex items-center justify-between px-3.5 py-2.5 bg-bg-secondary border border-border rounded-md cursor-pointer text-[0.9rem] font-medium text-text transition-all duration-200 select-none hover:border-text-muted hover:bg-bg-elevated ${isOpen ? 'border-primary ring-3 ring-primary/15' : ''}`} 
        onClick={() => setIsOpen(!isOpen)}
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && setIsOpen(!isOpen)}
      >
        <span className={!selectedOption ? 'text-text-muted' : ''}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDown size={16} className={`text-text-muted transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </div>
      
      {isOpen && (
        <div className="absolute top-[calc(100%+8px)] left-0 right-0 z-[1000] max-h-[300px] overflow-y-auto rounded-lg p-1.5 shadow-lg bg-bg-secondary/70 backdrop-blur-md border border-border animate-fade-in scrollbar-thin scrollbar-thumb-border">
          {options.map((option) => (
            <div 
              key={option.value} 
              className={`flex items-center justify-between px-3 py-2.5 rounded-md cursor-pointer text-[0.9rem] transition-all duration-200 text-text hover:bg-bg-elevated ${value === option.value ? 'bg-primary/10 text-primary font-semibold' : ''}`}
              onClick={() => handleSelect(option.value)}
            >
              <span>{option.label}</span>
              {value === option.value && <Check size={14} className="text-primary" />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Select;
