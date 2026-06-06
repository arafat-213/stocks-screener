import { useState, useRef } from 'react';
import { X, ChevronRight } from 'lucide-react';
import { getISTDateString } from '../utils/dateUtils';
import { size, isEmpty, map } from 'lodash/fp';
import { createJournalEntry, searchStocks } from '../api/client';

const ManualTradeModal = ({
  isOpen,
  onClose,
  onSuccess,
  initialData = null,
}) => {
  const [newTrade, setNewTrade] = useState(() => ({
    symbol: initialData?.symbol || '',
    entry_price: initialData?.price || '',
    shares: '1',
    stop_loss: initialData?.sl || '',
    target: initialData?.target || '',
    entry_date: getISTDateString(),
    notes: '',
    watchlist_id: initialData?.wlId || null,
  }));

  const [creating, setCreating] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const searchDebounceRef = useRef(null);

  const handleSymbolChange = (val) => {
    const upperVal = val.toUpperCase();
    setNewTrade({ ...newTrade, symbol: upperVal });

    if (searchDebounceRef.current) {
      clearTimeout(searchDebounceRef.current);
    }

    if (upperVal.length < 2) {
      setSearchResults([]);
      setShowResults(false);
      return;
    }

    setSearching(true);
    searchDebounceRef.current = setTimeout(async () => {
      try {
        const res = await searchStocks(upperVal);
        setSearchResults(res || []);
        setShowResults(true);
      } catch (err) {
        console.error('Search error:', err);
      } finally {
        setSearching(false);
      }
    }, 300);
  };

  const selectSymbol = (s) => {
    setNewTrade({ ...newTrade, symbol: s.symbol });
    setShowResults(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!newTrade.symbol || !newTrade.entry_price || !newTrade.shares) return;

    setCreating(true);
    try {
      let symbol = newTrade.symbol.toUpperCase().trim();
      // Auto-append .NS if missing and not an index
      if (!symbol.includes('.') && !symbol.startsWith('^')) {
        symbol = `${symbol}.NS`;
      }

      await createJournalEntry({
        ...newTrade,
        symbol: symbol,
        entry_price: parseFloat(newTrade.entry_price),
        shares: parseInt(newTrade.shares),
        stop_loss: newTrade.stop_loss ? parseFloat(newTrade.stop_loss) : null,
        target: newTrade.target ? parseFloat(newTrade.target) : null,
      });

      onSuccess();
      onClose();
    } catch (error) {
      console.error('Error creating journal entry:', error);
      alert('Failed to create trade. Please check console for details.');
    } finally {
      setCreating(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className='fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200'>
      <div className='bg-bg-secondary border border-border w-full max-w-lg rounded-3xl shadow-2xl animate-in zoom-in-95 duration-200 max-h-[90vh] overflow-y-auto'>
        <div className='flex justify-between items-center p-6 border-b border-border sticky top-0 bg-bg-secondary z-10'>
          <h3 className='text-xl font-black text-text uppercase tracking-tight'>
            New Trade Entry
          </h3>
          <button
            onClick={onClose}
            className='p-2 hover:bg-bg-elevated rounded-full transition-colors'
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className='p-6 flex flex-col gap-5'>
          <div className='grid grid-cols-2 gap-4'>
            <div className='flex flex-col gap-2 relative'>
              <label className='text-[10px] font-black uppercase tracking-widest text-text-muted ml-1'>
                Symbol
              </label>
              <input
                type='text'
                required
                value={newTrade.symbol}
                onChange={(e) => handleSymbolChange(e.target.value)}
                onFocus={() => size(searchResults) > 0 && setShowResults(true)}
                onBlur={() => setTimeout(() => setShowResults(false), 200)}
                className='w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50'
                placeholder='RELIANCE.NS'
                autoComplete='off'
              />

              {showResults && !isEmpty(searchResults) && (
                <div className='absolute top-[105%] left-0 right-0 bg-bg-secondary border border-border rounded-xl shadow-2xl z-[1000] max-h-[250px] overflow-y-auto animate-in fade-in slide-in-from-top-2 duration-200'>
                  {map((s) => (
                    <div
                      key={s.symbol}
                      className='p-3 hover:bg-bg-elevated cursor-pointer transition-colors border-b border-border last:border-none flex justify-between items-center'
                      onClick={() => selectSymbol(s)}
                    >
                      <div className='flex flex-col'>
                        <span className='font-black text-text text-sm'>
                          {s.symbol}
                        </span>
                        <span className='text-[10px] text-text-muted font-bold truncate max-w-[140px]'>
                          {s.name}
                        </span>
                      </div>
                      <div className='text-[9px] font-black text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded uppercase tracking-tighter'>
                        {s.sector}
                      </div>
                    </div>
                  ))(searchResults)}
                </div>
              )}

              {searching && (
                <div className='absolute right-3 top-[42px]'>
                  <div className='w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin'></div>
                </div>
              )}
            </div>
            <div className='flex flex-col gap-2'>
              <label className='text-[10px] font-black uppercase tracking-widest text-text-muted ml-1'>
                Entry Date
              </label>
              <input
                type='date'
                required
                value={newTrade.entry_date}
                onChange={(e) =>
                  setNewTrade({ ...newTrade, entry_date: e.target.value })
                }
                className='w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50'
              />
            </div>
          </div>

          <div className='grid grid-cols-2 gap-4'>
            <div className='flex flex-col gap-2'>
              <label className='text-[10px] font-black uppercase tracking-widest text-text-muted ml-1'>
                Entry Price (₹)
              </label>
              <input
                type='number'
                step='0.01'
                required
                value={newTrade.entry_price}
                onChange={(e) =>
                  setNewTrade({ ...newTrade, entry_price: e.target.value })
                }
                className='w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50'
                placeholder='0.00'
              />
            </div>
            <div className='flex flex-col gap-2'>
              <label className='text-[10px] font-black uppercase tracking-widest text-text-muted ml-1'>
                Shares
              </label>
              <input
                type='number'
                required
                min='1'
                value={newTrade.shares}
                onChange={(e) =>
                  setNewTrade({ ...newTrade, shares: e.target.value })
                }
                className='w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50'
                placeholder='1'
              />
            </div>
          </div>

          <div className='grid grid-cols-2 gap-4'>
            <div className='flex flex-col gap-2'>
              <label className='text-[10px] font-black uppercase tracking-widest text-text-muted ml-1'>
                Stop Loss (₹)
              </label>
              <input
                type='number'
                step='0.01'
                value={newTrade.stop_loss}
                onChange={(e) =>
                  setNewTrade({ ...newTrade, stop_loss: e.target.value })
                }
                className='w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50'
                placeholder='Optional'
              />
            </div>
            <div className='flex flex-col gap-2'>
              <label className='text-[10px] font-black uppercase tracking-widest text-text-muted ml-1'>
                Target (₹)
              </label>
              <input
                type='number'
                step='0.01'
                value={newTrade.target}
                onChange={(e) =>
                  setNewTrade({ ...newTrade, target: e.target.value })
                }
                className='w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50'
                placeholder='Optional'
              />
            </div>
          </div>

          <div className='flex flex-col gap-2'>
            <label className='text-[10px] font-black uppercase tracking-widest text-text-muted ml-1'>
              Notes
            </label>
            <textarea
              value={newTrade.notes}
              onChange={(e) =>
                setNewTrade({ ...newTrade, notes: e.target.value })
              }
              className='w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50 min-h-[80px]'
              placeholder='Why did you take this trade?'
            />
          </div>

          <button
            type='submit'
            disabled={creating}
            className='w-full bg-primary hover:bg-primary-dark disabled:opacity-50 text-white font-black py-4 rounded-2xl transition-all shadow-lg shadow-primary/20 flex items-center justify-center gap-2 mt-2'
          >
            {creating ? 'SAVING...' : 'SAVE TRADE ENTRY'}
            {!creating && <ChevronRight size={18} />}
          </button>
        </form>
      </div>
    </div>
  );
};

export default ManualTradeModal;
