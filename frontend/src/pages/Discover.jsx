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
  const [selectedSlug, setSelectedSlug] = useState('actionable-entries');
  const [liveMode, setLiveMode] = useState(false);
  const [capital, setCapital] = useState(1000000);
  const [riskPct, setRiskPct] = useState(3.0);

  // Fetch Strategy List
  const { 
    data: screens = [], 
    loading: loadingScreens 
  } = useFetch(getScreensList);

  // Fetch Strategy Results
  const fetchStrategyResults = useCallback(() => {
    const params = { live: liveMode };
    if (selectedSlug === 'actionable-entries') {
        params.capital = capital;
        params.risk_pct = riskPct;
    }
    return getScreenBySlug(selectedSlug, params).then(res => res.data);
  }, [selectedSlug, liveMode, capital, riskPct]);

  const {
    data: strategyResults = [],
    loading: loadingStrategyResults,
    refetch: refetchStrategy
  } = useFetch(fetchStrategyResults, {
    deps: [selectedSlug, capital, riskPct],
    refreshInterval: liveMode ? 10000 : null
  });

  return (
    <div className="w-full animate-fade-in">
      <header className="mb-8 sm:mb-12 flex flex-col sm:flex-row justify-between items-start sm:items-end gap-6">
        <div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tighter mb-2 uppercase">Market Discovery</h1>
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
          <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center bg-slate-50 dark:bg-slate-900/50 p-6 rounded-3xl border-2 border-border border-dashed gap-6">
              <div className="flex items-center gap-4">
                  <div className="bg-blue-500/10 p-2 rounded-xl">
                      <Zap size={24} className="text-blue-500" />
                  </div>
                  <div>
                      <h2 className="text-xl font-black uppercase tracking-tight m-0">{screens.find(s => s.slug === selectedSlug)?.label || 'Strategy Results'}</h2>
                      <p className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mt-1">Deep analysis updated every session.</p>
                  </div>
              </div>

              {selectedSlug === 'actionable-entries' && (
                <div className="flex flex-wrap items-center gap-6 bg-white dark:bg-slate-800 p-4 rounded-2xl border border-border shadow-sm">
                    <div className="flex flex-col gap-1">
                        <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">Trading Capital</label>
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-bold text-slate-400">₹</span>
                            <input 
                                type="number" 
                                value={capital} 
                                onChange={(e) => setCapital(Number(e.target.value))}
                                className="bg-transparent border-none text-sm font-black w-24 focus:outline-none"
                                step="50000"
                            />
                        </div>
                    </div>
                    <div className="w-px h-8 bg-border hidden sm:block" />
                    <div className="flex flex-col gap-1">
                        <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">Risk per Trade</label>
                        <div className="flex items-center gap-2">
                            <input 
                                type="number" 
                                value={riskPct} 
                                onChange={(e) => setRiskPct(Number(e.target.value))}
                                className="bg-transparent border-none text-sm font-black w-12 focus:outline-none"
                                step="0.5"
                                min="0.5"
                                max="10"
                            />
                            <span className="text-sm font-bold text-slate-400">%</span>
                        </div>
                    </div>
                </div>
              )}

              <div className="flex items-center gap-3 ml-auto lg:ml-0">
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
