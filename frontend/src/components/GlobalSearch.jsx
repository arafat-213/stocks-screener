import { useState, useEffect, useRef, useMemo } from 'react';
import { Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { fetchResults } from '../api/client';

export const GlobalSearch = () => {
  const [query, setQuery] = useState('');
  const [symbols, setSymbols] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const timeoutRef = useRef(null);

  useEffect(() => {
    // Fetch all symbols for full coverage
    fetchResults()
      .then(res => setSymbols(res.data.map(s => s.symbol)))
      .catch(err => console.error("Search fetch failed:", err));
    
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen(true);
      }
      if (e.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    if (isOpen) {
      // Focus after modal opens
      timeoutRef.current = setTimeout(() => inputRef.current?.focus(), 50);
    }
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [isOpen]);

  const filtered = useMemo(() => {
    return symbols
      .filter(s => s.toLowerCase().includes(query.toLowerCase()))
      .slice(0, 10);
  }, [symbols, query]);

  const handleSelect = (symbol) => {
    navigate(`/stocks/${symbol}`);
    setIsOpen(false);
    setQuery('');
  };

  return (
    <div className={`global-search ${isOpen ? 'open' : ''}`}>
      <div 
        className="search-trigger" 
        onClick={() => setIsOpen(true)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setIsOpen(true);
          }
        }}
      >
        <Search size={18} />
        <span>Search stocks...</span>
        <kbd>⌘K</kbd>
      </div>
      {isOpen && (
        <div className="search-overlay" onClick={() => setIsOpen(false)}>
          <div className="search-modal" onClick={e => e.stopPropagation()}>
            <div className="search-input-wrapper">
              <Search size={20} />
              <input 
                ref={inputRef}
                value={query} 
                onChange={e => setQuery(e.target.value)}
                placeholder="Search symbol (e.g. RELIANCE)..."
              />
            </div>
            <div className="results">
              {filtered.length > 0 ? (
                filtered.map(s => (
                  <div key={s} className="result-item" onClick={() => handleSelect(s)}>
                    {s.replace('.NS', '')}
                  </div>
                ))
              ) : (
                <div className="no-results">No stocks found</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GlobalSearch;
