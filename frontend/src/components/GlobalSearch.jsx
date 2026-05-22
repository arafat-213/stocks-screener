import { useState, useEffect, useRef } from 'react';
import { Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { searchStocks } from '../api/client';
import './GlobalSearch.css';

export const GlobalSearch = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]); // [{symbol, name, sector}]
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isOpen, setIsOpen] = useState(false);
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const debounceRef = useRef(null);
  
  // Keyboard event listeners
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Toggle search modal with Cmd/Ctrl + K
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen(prev => !prev);
      }
      
      // Close on Escape
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
      
      // Keyboard navigation when open
      if (isOpen) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setSelectedIndex(prev => 
            results.length > 0 ? Math.min(prev + 1, results.length - 1) : -1
          );
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setSelectedIndex(prev => Math.max(prev - 1, 0));
        }
        if (e.key === 'Enter' && selectedIndex >= 0) {
          e.preventDefault();
          handleSelect(results[selectedIndex].symbol);
        }
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, results, selectedIndex]);

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    } else {
      setQuery('');
      setResults([]);
      setSelectedIndex(-1);
    }
  }, [isOpen]);

  const handleQueryChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    setSelectedIndex(-1);
    
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    
    if (val.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    
    setLoading(true);
    debounceRef.current = setTimeout(() => {
      searchStocks(val)
        .then(res => {
          setResults(res.data);
          setLoading(false);
        })
        .catch(() => {
          setLoading(false);
        });
    }, 200);
  };

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
      >
        <Search size={18} />
        <span>Search stocks...</span>
        <kbd>⌘K</kbd>
      </div>
      
      {isOpen && (
        <div className="search-overlay" onClick={() => setIsOpen(false)}>
          <div className="search-modal" onClick={e => e.stopPropagation()}>
            <div className="search-input-wrapper">
              <Search size={20} className="text-text-muted" />
              <input 
                ref={inputRef}
                value={query} 
                onChange={handleQueryChange}
                placeholder="Search symbol or name (e.g. RELIANCE)..."
                autoComplete="off"
              />
            </div>
            
            <div className="results">
              {loading && query.length >= 2 && results.length === 0 ? (
                <div className="searching-state">Searching...</div>
              ) : results.length > 0 ? (
                results.map((s, i) => (
                  <div 
                    key={s.symbol} 
                    className={`result-item ${i === selectedIndex ? 'selected' : ''}`} 
                    onClick={() => handleSelect(s.symbol)}
                    onMouseEnter={() => setSelectedIndex(i)}
                  >
                    <div className="result-main">
                      <span className="result-symbol">{s.symbol}</span>
                      <span className="result-name text-text-muted">{s.name}</span>
                    </div>
                    <span className="result-sector text-xs text-text-muted">{s.sector}</span>
                  </div>
                ))
              ) : query.length >= 2 ? (
                <div className="no-results">No stocks found</div>
              ) : (
                <div className="search-hint">Type at least 2 characters...</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GlobalSearch;
