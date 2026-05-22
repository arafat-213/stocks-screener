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
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[1000] flex items-end justify-center sm:items-center p-0 sm:p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      
      <div className="relative w-full max-w-[500px] bg-bg-secondary rounded-t-[32px] sm:rounded-3xl shadow-2xl p-8 animate-fade-in border-t sm:border-2 border-border flex flex-col gap-8">
        <header className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="bg-blue-500/10 p-2 rounded-xl">
                <Filter size={20} className="text-blue-500" />
            </div>
            <h3 className="text-xl font-black uppercase tracking-tight">Market Filters</h3>
          </div>
          <button className="bg-slate-100 dark:bg-slate-800 p-2 rounded-full border-none cursor-pointer text-slate-500 hover:text-text transition-colors" onClick={onClose}>
            <X size={24} />
          </button>
        </header>

        <div className="flex flex-col gap-6 max-h-[60vh] overflow-y-auto pr-2">
          <section>
            <h4 className="text-[10px] font-black text-slate-500 dark:text-slate-400 mb-4 uppercase tracking-[0.2em]">Signal Confluence</h4>
            <div className="flex gap-2.5 flex-wrap">
              {['all', 'watchlist', '3', '2+'].map(c => (
                <button 
                  key={c} 
                  className={`border-2 px-5 py-3 rounded-2xl text-xs font-black uppercase tracking-widest cursor-pointer transition-all flex items-center gap-2 shadow-sm ${confluenceFilter === c ? 'bg-blue-600 text-white border-blue-600 shadow-blue-500/30' : 'bg-slate-50 dark:bg-slate-900/50 text-slate-500 border-transparent hover:border-slate-200'}`}
                  onClick={() => setConfluenceFilter(c)}
                >
                  {c === 'all' ? 'All Symbols' : c === 'watchlist' ? `Watchlist (${watchlistCount})` : c === '3' ? '3/3 High' : '2/3+ Mid'}
                </button>
              ))}
            </div>
          </section>

          <section>
            <h4 className="text-[10px] font-black text-slate-500 dark:text-slate-400 mb-4 uppercase tracking-[0.2em]">Market Sectors</h4>
            <div className="flex gap-2 flex-wrap">
              {availableSectors.map(sector => (
                <button 
                  key={sector} 
                  className={`border-2 px-4 py-2.5 rounded-xl text-[11px] font-bold uppercase tracking-tight cursor-pointer transition-all flex items-center gap-2 ${selectedSectors.includes(sector) ? 'bg-green-500 text-white border-green-500 shadow-lg shadow-green-500/20' : 'bg-slate-50 dark:bg-slate-900/50 text-slate-500 border-transparent hover:border-slate-200'}`}
                  onClick={() => toggleSector(sector)}
                >
                  {sector}
                </button>
              ))}
            </div>
          </section>
        </div>

        <div className="flex gap-3 pt-4 border-t border-border mt-auto">
          <button className="bg-slate-100 dark:bg-slate-800 text-text border-none p-4 rounded-2xl font-black uppercase tracking-widest text-[10px] cursor-pointer transition-all hover:bg-slate-200 dark:hover:bg-slate-700 flex items-center justify-center gap-2" onClick={resetFilters}>
            <RotateCcw size={16} /> Reset
          </button>
          <button className="flex-1 bg-blue-600 text-white border-none p-4 rounded-2xl font-black uppercase tracking-widest text-[10px] cursor-pointer transition-all hover:bg-blue-700 shadow-lg shadow-blue-500/20" onClick={onClose}>
            Apply Analysis
          </button>
        </div>
      </div>
    </div>
  );
};

export default FilterBottomSheet;
