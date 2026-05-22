import { useState, useMemo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { 
  RefreshCw, 
  Target,
  Zap,
  LayoutGrid
} from 'lucide-react';
import { 
  getScreenBySlug, 
  getScreensList
} from '../api/client';
import { useFetch } from '../hooks/useFetch';
import ScreenResultTable from '../components/ScreenResultTable';
import ScreenCard from '../components/ScreenCard';
import { ExportButton } from '../components/ui/ExportButton';

const Discover = () => {
  const [selectedSlug, setSelectedSlug] = useState('momentum-monsters');
  const [liveMode, setLiveMode] = useState(false);

  // Fetch Strategy List
  const { 
    data: screens = [], 
    loading: loadingScreens 
  } = useFetch(getScreensList);

  // Fetch Strategy Results
  const fetchStrategyResults = useCallback(() => {
    return getScreenBySlug(selectedSlug, liveMode).then(res => res.data);
  }, [selectedSlug, liveMode]);

  const {
    data: strategyResults = [],
    loading: loadingStrategyResults,
    refetch: refetchStrategy
  } = useFetch(fetchStrategyResults, {
    deps: [selectedSlug],
    refreshInterval: liveMode ? 10000 : null
  });

  return (
    <div className="max-w-[1500px] mx-auto p-6 animate-fade-in">
      <header className="mb-8 sm:mb-12 flex flex-col sm:flex-row justify-between items-start sm:items-end gap-6">
        <div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tighter mb-2">Market Discovery</h1>
          <p className="text-slate-500 dark:text-slate-400 font-bold uppercase tracking-widest text-xs">Explore expert screening strategies optimized for NSE.</p>
        </div>
      </header>

      <section className="flex flex-col gap-10">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {screens.map(screen => (
            <ScreenCard 
              key={screen.slug} 
              screen={screen} 
              isSelected={selectedSlug === screen.slug}
              onClick={() => setSelectedSlug(screen.slug)}
            />
          ))}
        </div>

        <div className="flex flex-col gap-6">
          <div className="flex justify-between items-center bg-slate-50 dark:bg-slate-900/50 p-6 rounded-3xl border-2 border-border border-dashed">
              <div className="flex items-center gap-4">
                  <div className="bg-blue-500/10 p-2 rounded-xl">
                      <Zap size={24} className="text-blue-500" />
                  </div>
                  <div>
                      <h2 className="text-xl font-black uppercase tracking-tight m-0">{screens.find(s => s.slug === selectedSlug)?.label || 'Strategy Results'}</h2>
                      <p className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mt-1">Deep analysis updated every session.</p>
                  </div>
              </div>
              <div className="flex items-center gap-3">
                <ExportButton 
                  data={strategyResults} 
                  columns={[]} 
                  filename={`${selectedSlug}-${new Date().toISOString().split('T')[0]}.csv`}
                  disabled={loadingStrategyResults}
                />
                <button 
                  onClick={() => setLiveMode(!liveMode)}
                  className={`flex items-center gap-2 py-2 px-4 rounded-xl text-[10px] font-black uppercase tracking-widest border-2 transition-all ${liveMode ? 'text-green-600 dark:text-green-400 border-green-500 bg-green-50 dark:bg-green-900/10 shadow-lg shadow-green-500/10' : 'text-slate-500 border-border hover:border-blue-500'}`}
                >
                  <RefreshCw size={14} className={loadingStrategyResults ? "animate-spin" : ""} />
                  Live Mode
                </button>
              </div>
          </div>
          
          <ScreenResultTable 
            results={strategyResults} 
            slug={selectedSlug}
            loading={loadingStrategyResults}
          />
        </div>
      </section>
    </div>
  );
};

export default Discover;
