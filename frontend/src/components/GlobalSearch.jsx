import { useState, useEffect, useRef } from 'react';
import { Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { map, size } from 'lodash/fp';
import { searchStocks } from '../api/client';

const mapWithIndex = map.convert({ cap: false });

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
        setIsOpen((prev) => !prev);
      }

      // Close on Escape
      if (e.key === 'Escape') {
        setIsOpen(false);
      }

      // Keyboard navigation when open
      if (isOpen) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setSelectedIndex((prev) =>
            size(results) > 0 ? Math.min(prev + 1, size(results) - 1) : -1
          );
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setSelectedIndex((prev) => Math.max(prev - 1, 0));
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
      if (debounceRef.current) clearTimeout(debounceRef.current);
    }
  }, [isOpen]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleQueryChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    setSelectedIndex(-1);

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (size(val) < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    debounceRef.current = setTimeout(() => {
      searchStocks(val)
        .then((res) => {
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
    <div className='relative z-[100] w-full flex justify-end'>
      {/* Desktop Search Bar */}
      <div
        className='hidden md:flex items-center gap-3 px-4 py-2.5 bg-bg-secondary border border-border rounded-md cursor-pointer transition-all duration-200 min-w-[240px] text-text-muted text-[0.9rem] hover:border-primary hover:text-text hover:shadow-sm'
        onClick={() => setIsOpen(true)}
        role='button'
        tabIndex={0}
      >
        <Search size={18} />
        <span>Search stocks...</span>
        <kbd className='ml-auto bg-bg-elevated px-1.5 py-0.5 rounded-sm text-[0.7rem] font-mono border border-border'>
          ⌘K
        </kbd>
      </div>

      {/* Mobile Search Icon */}
      <button
        className='flex md:hidden p-2 text-text-muted hover:text-text active:scale-95 transition-transform'
        onClick={() => setIsOpen(true)}
      >
        <Search size={22} />
      </button>

      {isOpen && (
        <div
          className='fixed inset-0 bg-black/40 backdrop-blur-md flex justify-center pt-[10vh] z-[1000]'
          onClick={() => setIsOpen(false)}
        >
          <div
            className='w-full max-w-[500px] bg-bg-secondary border border-border rounded-lg shadow-lg overflow-hidden flex flex-col h-fit animate-fade-in'
            onClick={(e) => e.stopPropagation()}
          >
            <div className='flex items-center gap-3 p-4 border-b border-border'>
              <Search size={20} className='text-text-muted' />
              <input
                ref={inputRef}
                value={query}
                onChange={handleQueryChange}
                placeholder='Search symbol or name (e.g. RELIANCE)...'
                autoComplete='off'
                className='flex-1 border-none text-[1.1rem] p-0 bg-transparent text-text focus:outline-none focus:ring-0'
              />
            </div>

            <div className='max-h-[400px] overflow-y-auto p-2 scrollbar-thin scrollbar-thumb-border'>
              {loading && size(query) >= 2 && size(results) === 0 ? (
                <div className='p-6 text-center text-text-muted'>
                  Searching...
                </div>
              ) : size(results) > 0 ? (
                mapWithIndex(
                  (s, i) => (
                    <div
                      key={s.symbol}
                      className={`px-3 py-2.5 cursor-pointer flex justify-between items-center rounded-sm transition-all duration-200 hover:bg-bg-elevated ${i === selectedIndex ? 'bg-bg-elevated' : ''}`}
                      onClick={() => handleSelect(s.symbol)}
                      onMouseEnter={() => setSelectedIndex(i)}
                    >
                      <div className='flex items-baseline'>
                        <span className='font-semibold text-[0.9rem] text-text'>
                          {s.symbol}
                        </span>
                        <span className='text-[0.8rem] ml-2 text-text-muted'>
                          {s.name}
                        </span>
                      </div>
                      <span className='text-[0.75rem] text-text-muted'>
                        {s.sector}
                      </span>
                    </div>
                  ),
                  results
                )
              ) : size(query) >= 2 ? (
                <div className='p-6 text-center text-text-muted'>
                  No stocks found
                </div>
              ) : (
                <div className='p-6 text-center text-text-muted'>
                  Type at least 2 characters...
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GlobalSearch;
