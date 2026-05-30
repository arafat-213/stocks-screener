import { useState, useCallback } from 'react';
import { RefreshCw, Zap, ChevronDown, Filter } from 'lucide-react';
import { getScreenBySlug, getScreensList } from '../api/client';
import { useFetch } from '../hooks/useFetch';
import ScreenResultTable from '../components/ScreenResultTable';
import ScreenCard from '../components/ScreenCard';
import { ExportButton } from '../components/ui/ExportButton';
import BottomSheet from '../components/ui/BottomSheet';

const Discover = () => {
  const [selectedSlug, setSelectedSlug] = useState('actionable-entries');
  const [liveMode, setLiveMode] = useState(false);
  const [capital, setCapital] = useState(1000000);
  const [riskPct, setRiskPct] = useState(3.0);
  const [isBottomSheetOpen, setIsBottomSheetOpen] = useState(false);

  const [showMobileSettings, setShowMobileSettings] = useState(false);

  // Fetch Strategy List
  const { data: screens = [] } = useFetch(getScreensList);

  const selectedScreen = screens.find((s) => s.slug === selectedSlug);

  // Fetch Strategy Results
  const fetchStrategyResults = useCallback(
    () => getScreenBySlug(selectedSlug, { live: liveMode }),
    [selectedSlug, liveMode]
  );

  const { data: strategyResults = [], loading: loadingStrategyResults } =
    useFetch(fetchStrategyResults, { deps: [selectedSlug, liveMode] });
  const handleScreenSelect = (slug) => {
    setSelectedSlug(slug);
    setIsBottomSheetOpen(false);
    setShowMobileSettings(false);
  };

  return (
    <div className='w-full animate-fade-in pb-24 lg:pb-0'>
      <header className='mb-8 sm:mb-10 flex flex-col sm:flex-row justify-between items-start sm:items-end gap-6'>
        <div>
          <h1 className='text-3xl sm:text-4xl font-black tracking-tighter mb-2 uppercase'>
            Market Discovery
          </h1>
          <p className='text-slate-500 dark:text-slate-400 font-bold uppercase tracking-widest text-xs'>
            Explore expert screening strategies optimized for NSE.
          </p>
        </div>
      </header>

      <section className='flex flex-col gap-6 sm:gap-8'>
        {/* Desktop Grid - Visible only on LG and up */}
        <div className='hidden lg:grid grid-cols-4 gap-4'>
          {screens.map((screen) => (
            <ScreenCard
              key={screen.slug}
              screen={screen}
              isSelected={selectedSlug === screen.slug}
              onClick={() => handleScreenSelect(screen.slug)}
            />
          ))}
        </div>

        {/* Mobile/Tablet Compact Selection Header */}
        <div className='lg:hidden'>
          <button
            onClick={() => setIsBottomSheetOpen(true)}
            className='w-full flex items-center justify-between p-4 bg-white dark:bg-slate-900 border-2 border-border rounded-2xl hover:border-blue-500 transition-all shadow-sm group'
          >
            <div className='flex items-center gap-3 text-left'>
              <div className='bg-blue-500/10 p-2 rounded-xl group-hover:bg-blue-500/20 transition-colors'>
                <Filter size={18} className='text-blue-500' />
              </div>
              <h3 className='text-base font-black uppercase tracking-tight'>
                {selectedScreen?.label || 'Select Strategy'}
              </h3>
            </div>
            <div className='flex items-center gap-2'>
              <span className='text-[10px] font-black uppercase tracking-widest text-slate-400'>
                Change
              </span>
              <ChevronDown size={18} className='text-slate-400' />
            </div>
          </button>
        </div>

        {/* Bottom Sheet for selection */}
        <BottomSheet
          isOpen={isBottomSheetOpen}
          onClose={() => setIsBottomSheetOpen(false)}
          title='Select Strategy'
        >
          <div className='flex flex-col gap-3 py-2'>
            {screens.map((screen) => (
              <ScreenCard
                key={screen.slug}
                screen={screen}
                isSelected={selectedSlug === screen.slug}
                onClick={() => handleScreenSelect(screen.slug)}
              />
            ))}
          </div>
        </BottomSheet>

        <div className='flex flex-col'>
          {/* DESKTOP FLUSH TOOLBAR */}
          <div className='hidden lg:flex items-center justify-between bg-slate-50 dark:bg-slate-900/50 px-6 py-3 rounded-t-2xl border-2 border-b-0 border-border border-dashed'>
            <div className='flex items-center gap-6'>
              <button
                onClick={() => setLiveMode(!liveMode)}
                className={`flex items-center gap-2 py-1.5 px-3 rounded-lg text-[9px] font-black uppercase tracking-widest border-2 transition-all ${liveMode ? 'text-green-600 dark:text-green-400 border-green-500 bg-green-50 dark:bg-green-900/10' : 'text-slate-500 border-border hover:border-blue-500'}`}
              >
                <div
                  className={`w-1.5 h-1.5 rounded-full ${liveMode ? 'bg-green-500 animate-pulse' : 'bg-slate-300'}`}
                />
                Live Mode
              </button>

              {selectedSlug === 'actionable-entries' && (
                <div className='flex items-center gap-6 text-slate-500'>
                  <div className='flex items-center gap-3'>
                    <label className='text-[9px] font-black uppercase tracking-widest text-slate-400'>
                      Capital
                    </label>
                    <div className='flex items-center gap-1 bg-white dark:bg-slate-800 px-2 py-1 rounded-md border border-border'>
                      <span className='text-[10px] font-bold'>₹</span>
                      <input
                        type='number'
                        value={capital}
                        onChange={(e) => setCapital(Number(e.target.value))}
                        className='bg-transparent border-none text-[11px] font-black w-20 focus:outline-none'
                        step='50000'
                      />
                    </div>
                  </div>
                  <div className='flex items-center gap-3'>
                    <label className='text-[9px] font-black uppercase tracking-widest text-slate-400'>
                      Risk
                    </label>
                    <div className='flex items-center gap-1 bg-white dark:bg-slate-800 px-2 py-1 rounded-md border border-border'>
                      <input
                        type='number'
                        value={riskPct}
                        onChange={(e) => setRiskPct(Number(e.target.value))}
                        className='bg-transparent border-none text-[11px] font-black w-8 focus:outline-none'
                        step='0.5'
                        min='0.5'
                        max='10'
                      />
                      <span className='text-[10px] font-bold'>%</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <ExportButton
              data={strategyResults}
              columns={[]}
              filename={`${selectedSlug}-${new Date().toISOString().split('T')[0]}.csv`}
              disabled={loadingStrategyResults}
            />
          </div>

          <ScreenResultTable
            results={strategyResults}
            slug={selectedSlug}
            loading={loadingStrategyResults}
          />
        </div>
      </section>

      {/* MOBILE STICKY CONTEXT BAR (FAB) */}
      <div className='lg:hidden fixed bottom-24 left-4 right-4 z-[70] flex flex-col items-center gap-3'>
        {/* Expanded Settings (only on mobile when toggled) */}
        {showMobileSettings && selectedSlug === 'actionable-entries' && (
          <div className='w-full bg-white dark:bg-slate-900 p-4 rounded-2xl border-2 border-border shadow-2xl animate-slide-up'>
            <div className='grid grid-cols-2 gap-4'>
              <div className='flex flex-col gap-1.5'>
                <label className='text-[9px] font-black uppercase tracking-widest text-slate-400'>
                  Capital
                </label>
                <div className='flex items-center gap-2 bg-slate-50 dark:bg-slate-800 p-3 rounded-xl border border-border'>
                  <span className='font-bold text-slate-400'>₹</span>
                  <input
                    type='number'
                    value={capital}
                    onChange={(e) => setCapital(Number(e.target.value))}
                    className='bg-transparent border-none text-sm font-black w-full focus:outline-none'
                  />
                </div>
              </div>
              <div className='flex flex-col gap-1.5'>
                <label className='text-[9px] font-black uppercase tracking-widest text-slate-400'>
                  Risk %
                </label>
                <div className='flex items-center gap-2 bg-slate-50 dark:bg-slate-800 p-3 rounded-xl border border-border'>
                  <input
                    type='number'
                    value={riskPct}
                    onChange={(e) => setRiskPct(Number(e.target.value))}
                    className='bg-transparent border-none text-sm font-black w-full focus:outline-none'
                  />
                  <span className='font-bold text-slate-400'>%</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Main FAB Bar */}
        <div className='w-full max-w-sm bg-white/80 dark:bg-slate-900/80 backdrop-blur-md px-4 py-3 rounded-full border-2 border-border shadow-2xl flex items-center justify-between gap-2'>
          <button
            onClick={() => setLiveMode(!liveMode)}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all ${liveMode ? 'bg-green-500 text-white shadow-lg shadow-green-500/20' : 'bg-slate-100 dark:bg-slate-800 text-slate-500'}`}
          >
            <RefreshCw
              size={14}
              className={loadingStrategyResults ? 'animate-spin' : ''}
            />
            {liveMode ? 'Live' : 'Go Live'}
          </button>

          {selectedSlug === 'actionable-entries' && (
            <button
              onClick={() => setShowMobileSettings(!showMobileSettings)}
              className={`p-2.5 rounded-full transition-all border-2 ${showMobileSettings ? 'bg-blue-500 border-blue-500 text-white' : 'bg-slate-100 dark:bg-slate-800 border-transparent text-slate-500'}`}
            >
              <Zap size={18} />
            </button>
          )}

          <div className='flex-1'>
            <ExportButton
              data={strategyResults}
              columns={[]}
              filename={`${selectedSlug}-${new Date().toISOString().split('T')[0]}.csv`}
              disabled={loadingStrategyResults}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Discover;
