import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';
import './Select.css';

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
    <div className={`custom-select-container ${className}`} ref={dropdownRef}>
      {label && <label className="select-label">{label}</label>}
      <div 
        className={`select-trigger ${isOpen ? 'active' : ''}`} 
        onClick={() => setIsOpen(!isOpen)}
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && setIsOpen(!isOpen)}
      >
        <span className={!selectedOption ? 'placeholder' : ''}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDown size={16} className={`chevron ${isOpen ? 'open' : ''}`} />
      </div>
      
      {isOpen && (
        <div className="select-dropdown glass">
          {options.map((option) => (
            <div 
              key={option.value} 
              className={`select-option ${value === option.value ? 'selected' : ''}`}
              onClick={() => handleSelect(option.value)}
            >
              <span>{option.label}</span>
              {value === option.value && <Check size={14} className="check-icon" />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Select;
