import { X, Filter, RotateCcw } from 'lucide-react';

const FilterBottomSheet = ({ 
  isOpen, 
  onClose, 
  confluenceFilter, 
  setConfluenceFilter, 
  availableSectors, 
  selectedSectors, 
  toggleSector, 
  resetFilters,
  watchlistCount
}) => {
  return (
    <div 
      className={`fixed inset-0 bg-black/40 backdrop-blur-sm z-[2000] flex items-end transition-all duration-300 ${isOpen ? 'opacity-100 visible' : 'opacity-0 invisible'}`} 
      onClick={onClose}
    >
      <div 
        className={`w-full bg-bg-secondary rounded-t-[24px] p-6 transition-transform duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] max-h-[85vh] flex flex-col shadow-lg ${isOpen ? 'translate-y-0' : 'translate-y-full'}`} 
        onClick={e => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-3">
            <Filter size={18} />
            <h3 className="text-[18px] font-bold text-text">Filters</h3>
          </div>
          <button className="bg-bg-elevated border-none text-text-muted cursor-pointer p-2 rounded-full flex items-center justify-center hover:bg-bg-secondary transition-colors" onClick={onClose}>
            <X size={24} />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 pb-6">
          <div className="mb-8">
            <h4 className="text-[12px] font-bold text-text-muted mb-4 uppercase tracking-widest">Confluence</h4>
            <div className="flex gap-2 flex-wrap">
              {['all', 'watchlist', '3', '2+'].map(c => (
                <button 
                  key={c} 
                  className={`bg-bg-elevated border border-border px-[18px] py-[10px] rounded-[12px] text-[14px] font-semibold cursor-pointer transition-all duration-200 text-text flex items-center gap-2 ${confluenceFilter === c ? 'bg-bullish/10 text-bullish border-bullish shadow-none after:content-["✓"] after:text-[12px] after:font-extrabold' : ''}`}
                  onClick={() => setConfluenceFilter(c)}
                >
                  {c === 'all' ? 'All Stocks' : c === 'watchlist' ? `Watchlist (${watchlistCount})` : c === '3' ? '3/3 Only' : '2/3+'}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-8">
            <div className="flex justify-between items-center mb-4">
              <h4 className="text-[12px] font-bold text-text-muted uppercase tracking-widest">Sectors</h4>
              <span className="text-[11px] bg-bg-elevated px-2 py-0.5 rounded-lg text-text-muted font-semibold">{availableSectors.length}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {availableSectors.map(sector => (
                <button 
                  key={sector} 
                  className={`bg-bg-elevated border border-border px-[18px] py-[10px] rounded-[12px] text-[14px] font-semibold cursor-pointer transition-all duration-200 text-text flex items-center gap-2 ${selectedSectors.includes(sector) ? 'bg-bullish/10 text-bullish border-bullish shadow-none after:content-["✓"] after:text-[12px] after:font-extrabold' : ''}`}
                  onClick={() => toggleSector(sector)}
                >
                  {sector}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex gap-3 pt-5 border-t border-border bg-bg-secondary">
          <button className="flex items-center justify-center gap-2 bg-none border border-border px-5 py-3.5 rounded-[14px] font-bold cursor-pointer text-text text-[15px] hover:bg-bg-elevated transition-colors" onClick={resetFilters}>
            <RotateCcw size={16} />
            Reset
          </button>
          <button className="flex-1 bg-text text-bg-secondary border-none p-3.5 rounded-[14px] font-bold cursor-pointer text-[15px] dark:bg-white dark:text-black transition-opacity hover:opacity-90" onClick={onClose}>
            Apply Filters
          </button>
        </div>
      </div>
    </div>
  );
};

export default FilterBottomSheet;
