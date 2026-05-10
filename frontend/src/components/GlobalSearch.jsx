import { useState, useEffect, useRef } from 'react';
import { Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { fetchResults } from '../api/client';

export const GlobalSearch = () => {
  const [query, setQuery] = useState('');
  const [symbols, setSymbols] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const navigate = useNavigate();
  const inputRef = useRef(null);

  useEffect(() => {
    // Fetch all symbols for full coverage
    fetchResults().then(res => setSymbols(res.data.map(s => s.symbol)));
    
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
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  const filtered = symbols
    .filter(s => s.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 10);

  const handleSelect = (symbol) => {
    navigate(`/stocks/${symbol}`);
    setIsOpen(false);
    setQuery('');
  };

  return (
    <div className={`global-search ${isOpen ? 'open' : ''}`}>
      <div className="search-trigger" onClick={() => setIsOpen(true)}>
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
