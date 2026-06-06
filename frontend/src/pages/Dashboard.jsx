import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import Play from 'lucide-react/dist/esm/icons/play';
import Filter from 'lucide-react/dist/esm/icons/filter';
import ArrowUpDown from 'lucide-react/dist/esm/icons/arrow-up-down';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import LayoutGrid from 'lucide-react/dist/esm/icons/layout-grid';
import List from 'lucide-react/dist/esm/icons/list';
import RefreshCcw from 'lucide-react/dist/esm/icons/refresh-ccw';
import { Link } from 'react-router-dom';
import map from 'lodash/fp/map';
import size from 'lodash/fp/size';
import times from 'lodash/fp/times';
import uniqBy from 'lodash/fp/uniqBy';
import {
  fetchResults,
  getDashboardChanges,
  addToWatchlist,
  removeFromWatchlist,
} from '../api/client';
import { useFetch } from '../hooks/useFetch';
import { usePipeline } from '../hooks/usePipeline';
import { useMarketData } from '../hooks/useMarketData';
import { useWatchlist } from '../hooks/useWatchlist';
import StockCard from '../components/StockCard';
import StockCardSkeleton from '../components/StockCardSkeleton';
import FilterBottomSheet from '../components/FilterBottomSheet';
import GlobalSearch from '../components/GlobalSearch';
import Select from '../components/ui/Select';
import { DataTable } from '../components/ui/DataTable';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import StaleBanner from '../components/StaleBanner';
import ChangeBanner from '../components/ChangeBanner';
import WatchlistStar from '../components/WatchlistStar';
import PipelineProgress from '../components/PipelineProgress';
import SetupBadge from '../components/SetupBadge';
import HighConvictionDigest from '../components/HighConvictionDigest';

const DEFAULT_SORT = { key: 'score', direction: 'desc' };

const Dashboard = () => {
  // Data Fetching Hooks
  const [stocks, setStocks] = useState([]);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const {
    data: changesData,
    loading: changesLoading,
    refetch: refetchChanges,
  } = useFetch(getDashboardChanges);

  const {
    status,
    stats: pipeline,
    isBusy,
    run: handleRunPipeline,
    stop: handleStopPipeline,
    error: pipelineError,
  } = usePipeline();

  const { market_context, error: marketError } = useMarketData();
  const { watchlist, toggle, isWatched, count } = useWatchlist();

  const handleToggleWatchlist = useCallback(
    async (row) => {
      const symbol = row.symbol;
      const isAlreadyWatched = isWatched(symbol);

      try {
        if (isAlreadyWatched) {
          await removeFromWatchlist(symbol);
        } else {
          await addToWatchlist({
            symbol: symbol,
            signal_date: row.date || new Date().toISOString().split('T')[0],
            quality_tier: row.quality_tier || 'A',
            signal_score: row.timeframes?.D?.score || row.score,
          });
        }
        toggle(symbol);
      } catch (err) {
        alert(`Failed to update watchlist: ${err.message}`);
      }
    },
    [isWatched, toggle]
  );

  // Filters and Sort State
  const [confluenceFilter, setConfluenceFilter] = useState('all'); // 'all', 'watchlist', '3', '2+'
  const [selectedSectors, setSelectedSectors] = useState([]);
  const [sortBy, setSortBy] = useState('confluence'); // 'confluence', 'score', 'rsi', 'pe'
  const [viewMode, setViewMode] = useState('table'); // 'grid', 'table'

  // Responsiveness State
  const [isFilterSheetOpen, setIsFilterSheetOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

  const loadMore = useCallback(
    async (isReset = false, showLoading = true) => {
      if (loading || (!hasMore && !isReset)) return;

      if (showLoading) setLoading(true);
      const currentOffset = isReset ? 0 : offset;

      try {
        const data = await fetchResults({
          offset: currentOffset,
          limit: 50,
          sector: selectedSectors.join(','),
          confluence:
            confluenceFilter === 'watchlist' ? undefined : confluenceFilter,
          symbols:
            confluenceFilter === 'watchlist'
              ? [...watchlist].join(',')
              : undefined,
          sort_by: sortBy,
        });

        if (isReset) {
          setStocks(data.items);
          setOffset(50);
        } else {
          setStocks((prev) => uniqBy('symbol', [...prev, ...data.items]));
          setOffset(currentOffset + 50);
        }

        setHasMore(data.has_more);
        setError(null);
      } catch (err) {
        setError(err.message || 'Failed to fetch stocks');
      } finally {
        setLoading(false);
      }
    },
    [
      offset,
      hasMore,
      loading,
      selectedSectors,
      confluenceFilter,
      sortBy,
      watchlist,
    ]
  );

  // Infinite Scroll Trigger
  const sentinelRef = useRef(null);
  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          loadMore();
        }
      },
      { threshold: 0.1 }
    );

    if (sentinelRef.current) obs.observe(sentinelRef.current);
    return () => obs.disconnect();
  }, [hasMore, loading, loadMore]);

  // Filter/Sort Integration
  useEffect(() => {
    const timer = setTimeout(() => {
      loadMore(true, false);
    }, 0);
    return () => clearTimeout(timer);
  }, [selectedSectors, confluenceFilter, sortBy, loadMore]);

  // Implement refresh side-effect: when status transitions from running to complete, call loadMore(true)
  const prevStatusRef = useRef(status);
  useEffect(() => {
    if (prevStatusRef.current === 'running' && status === 'complete') {
      loadMore(true);
      refetchChanges();
    }
    prevStatusRef.current = status;
  }, [status, loadMore, refetchChanges]);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setViewMode('grid');
    };
    window.addEventListener('resize', handleResize);
    // Initial check
    handleResize();
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Derived: Available Sectors (optimized single pass)
  const availableSectors = useMemo(() => {
    if (stocks.length === 0) return [];
    const sectors = new Set();
    for (const stock of stocks) {
      if (stock.sector) sectors.add(stock.sector);
    }
    return Array.from(sectors).sort();
  }, [stocks]);

  // Column Definitions for DataTable
  const columns = useMemo(
    () => [
      {
        key: 'watchlist',
        label: '★',
        sortable: false,
        render: (_, row) => (
          <WatchlistStar
            symbol={row.symbol}
            isWatched={isWatched(row.symbol)}
            onToggle={() => handleToggleWatchlist(row)}
          />
        ),
      },
      {
        key: 'symbol',
        label: 'Symbol',
        sortable: true,
        render: (val) => (
          <Link
            to={`/stocks/${val}`}
            className='text-blue-600 dark:text-blue-400 font-black no-underline hover:underline transition-all tracking-tighter'
          >
            {val.replace('.NS', '')}
          </Link>
        ),
      },
      {
        key: 'setup',
        label: 'Setup',
        sortable: true,
        accessor: (row) => row.setup?.setup_type || '',
        render: (_, row) => <SetupBadge setup={row.setup} />,
      },
      {
        key: 'close_price',
        label: 'Price',
        sortable: true,
        render: (val) =>
          `₹${val?.toLocaleString('en-IN', { minimumFractionDigits: 1 })}`,
      },
      {
        key: 'price_change_pct',
        label: 'Change %',
        sortable: true,
        render: (val) => (
          <span
            className={`px-2 py-1 rounded-md font-mono font-bold text-xs ${val >= 0 ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'}`}
          >
            {val >= 0 ? '+' : ''}
            {val?.toFixed(2)}%
          </span>
        ),
      },
      {
        key: 'score',
        label: 'Score',
        sortable: true,
        accessor: (row) => row.timeframes?.D?.score || 0,
        render: (val) => (
          <span
            className={`font-black text-sm px-2 py-1 rounded ${val >= 70 ? 'bg-green-500 text-white' : val >= 50 ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'}`}
          >
            {val || '-'}
          </span>
        ),
      },
      {
        key: 'rs_score',
        label: 'RS',
        sortable: true,
        accessor: (row) => row.timeframes?.D?.rs_score || 0,
        render: (val) => (
          <span
            className={`font-black text-sm ${val >= 80 ? 'text-green-600 dark:text-green-400' : 'text-blue-600 dark:text-blue-400'}`}
          >
            {val?.toFixed(0) || '-'}
          </span>
        ),
      },
      {
        key: 'adx',
        label: 'ADX',
        sortable: true,
        accessor: (row) => row.timeframes?.D?.adx || 0,
        render: (val) => val?.toFixed(1) || '-',
      },
      {
        key: 'sector',
        label: 'Sector',
        sortable: true,
      },
    ],
    [isWatched, handleToggleWatchlist]
  );

  const toggleSector = (sector) => {
    setSelectedSectors((prev) =>
      prev.includes(sector)
        ? prev.filter((s) => s !== sector)
        : [...prev, sector]
    );
  };

  const resetFilters = () => {
    setConfluenceFilter('all');
    setSelectedSectors([]);
  };

  // Optimized Market Data Lookups
  const marketMap = useMemo(() => {
    const map = new Map();
    if (market_context) {
      for (const m of market_context) {
        map.set(m.symbol, m);
      }
    }
    return map;
  }, [market_context]);

  const nifty = marketMap.get('^NSEI') || {};
  const sensex = marketMap.get('^BSESN') || {};

  const isNiftyUp = nifty.change_pct >= 0;
  const isSensexUp = sensex.change_pct >= 0;

  const hasMarketData = marketMap.size > 0;

  const hasData = size(stocks) > 0;

  if (loading && !hasData) {
    return (
      <div className='w-full'>
        <main className='flex-1'>
          <div className='grid grid-cols-2 lg:grid-cols-4 gap-4'>
            {map(
              (i) => (
                <div
                  key={i}
                  className='bg-bg-secondary p-4 rounded-xl border border-border flex flex-col gap-1'
                >
                  <div className='h-10 w-full bg-bg-elevated rounded-md animate-pulse'></div>
                </div>
              ),
              [1, 2, 3, 4]
            )}
          </div>
          <div className='mt-8'>
            {viewMode === 'grid' ? (
              <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6'>
                {map(
                  (i) => (
                    <StockCardSkeleton key={i} />
                  ),
                  [1, 2, 3, 4, 5, 6]
                )}
              </div>
            ) : (
              <div className='bg-bg-secondary rounded-xl border border-border mt-4 overflow-hidden'>
                <div className='flex bg-bg-elevated border-bottom border-border min-w-fit'>
                  {map(
                    (col) => (
                      <div
                        key={col.key}
                        className='px-4 py-3 text-[11px] font-bold text-text-muted uppercase tracking-wider flex items-center gap-2 flex-1 min-w-[120px]'
                      >
                        {col.label}
                      </div>
                    ),
                    columns
                  )}
                </div>
                {times(
                  (i) => (
                    <div
                      key={i}
                      className='flex border-b border-border transition-colors hover:bg-bg-elevated'
                    >
                      {map(
                        (col) => (
                          <div
                            key={col.key}
                            className='p-4 text-sm text-text flex-1 min-w-[120px] flex items-center'
                          >
                            <div className='h-4 w-full bg-bg-elevated rounded-sm animate-pulse' />
                          </div>
                        ),
                        columns
                      )}
                    </div>
                  ),
                  10
                )}
              </div>
            )}
          </div>
        </main>
      </div>
    );
  }

  if (pipeline?.status === 'never_run') {
    return (
      <div className='flex flex-col items-center justify-center py-20 text-center text-text-muted'>
        <AlertCircle size={64} />
        <h1 className='text-text my-4 text-2xl font-bold'>No Data Available</h1>
        <p>
          The pipeline hasn't been run yet. Start it to see market analysis.
        </p>
        <button
          className='mt-8 bg-blue-600 text-white border-none py-4 px-8 rounded-2xl font-black uppercase tracking-[0.2em] text-xs flex items-center gap-3 cursor-pointer transition-all hover:bg-blue-700 shadow-lg shadow-blue-500/20 active:scale-[0.98]'
          onClick={() => handleRunPipeline()}
          disabled={isBusy}
        >
          <Play size={18} fill='currentColor' /> Initialize Analysis Engine
        </button>
      </div>
    );
  }

  return (
    <div className='w-full animate-fade-in'>
      {error || pipelineError || marketError ? (
        <ErrorBanner message={error || pipelineError || marketError} />
      ) : null}

      {pipeline?.is_stale ? (
        <StaleBanner
          lastUpdated={pipeline.scored_at}
          dataAgeHours={pipeline.data_age_hours}
          onRunPipeline={handleRunPipeline}
          isBusy={isBusy}
        />
      ) : null}

      {!hasMarketData && !loading ? (
        <div className='bg-bg-secondary p-4 mb-4 rounded-lg border border-border text-text-muted'>
          Market data is currently unavailable.
        </div>
      ) : null}

      {/* Main Content */}
      <main className='flex-1'>
        <header className='mb-8 sm:mb-10 flex flex-col gap-6'>
          <div className='flex flex-col sm:flex-row justify-between items-start sm:items-end gap-6'>
            <div>
              <h1 className='text-3xl sm:text-4xl font-black tracking-tighter mb-1 uppercase'>
                Market Dashboard
              </h1>
            </div>
            {!isMobile ? <GlobalSearch /> : null}
          </div>

          <div className='grid grid-cols-2 lg:grid-cols-4 gap-4'>
            {status === 'running' ? (
              <div className='bg-blue-600 border-2 border-blue-700 p-5 rounded-2xl flex flex-col gap-4 shadow-lg shadow-blue-500/20 col-span-1 sm:col-span-2 lg:col-span-1 animate-fade-in'>
                <div className='flex justify-between items-start'>
                  <div className='flex flex-col gap-0.5'>
                    <span className='text-[9px] font-black text-white/70 uppercase tracking-[0.2em]'>
                      Live Analysis
                    </span>
                    <div className='flex items-center gap-2'>
                      <RefreshCcw
                        size={14}
                        className='animate-spin text-white'
                      />
                      <span className='text-sm font-black text-white uppercase tracking-tight'>
                        Engine Active
                      </span>
                    </div>
                  </div>
                  <button
                    className='bg-white/20 hover:bg-white/30 text-white border-none py-1 px-2.5 rounded-lg font-black text-[9px] uppercase tracking-tighter cursor-pointer transition-colors backdrop-blur-md'
                    onClick={handleStopPipeline}
                    disabled={status === 'stopping'}
                  >
                    {status === 'stopping' ? 'Stopping' : 'Stop'}
                  </button>
                </div>

                <div className='flex flex-col'>
                  <div className='flex justify-between items-end mb-1'>
                    <span className='text-[10px] font-black text-white'>
                      PROGRESS
                    </span>
                    <span className='text-[10px] font-black text-white'>
                      {pipeline?.stocks_scored || 0} /{' '}
                      {pipeline?.tier1_count || 0}
                    </span>
                  </div>
                  <PipelineProgress
                    fetched={pipeline?.stocks_fetched || 0}
                    scored={pipeline?.stocks_scored || 0}
                    total={pipeline?.total_symbols || 0}
                    tier1Count={pipeline?.tier1_count || 0}
                  />
                </div>
              </div>
            ) : null}
            <div className='bg-bg-secondary p-5 rounded-2xl border-2 border-border shadow-sm flex items-center gap-2 transition-colors hover:border-blue-500/30'>
              <span className='text-[10px] uppercase text-slate-500 dark:text-slate-400 tracking-[0.2em] font-black'>
                Nifty 50
              </span>
              <div className='flex gap-4 items-center'>
                <span className='text-2xl font-black text-text tracking-tighter'>
                  {nifty.close?.toLocaleString('en-IN')}
                </span>
                <span
                  className={`text-xs font-black px-2 py-0.5 rounded-full w-fit mt-1 ${isNiftyUp ? 'bg-green-500 text-white shadow-lg shadow-green-500/20' : 'bg-red-500 text-white shadow-lg shadow-red-500/20'}`}
                >
                  {isNiftyUp ? '▲' : '▼'}{' '}
                  {Math.abs(nifty.change_pct)?.toFixed(2)}%
                </span>
              </div>
            </div>
            <div className='bg-bg-secondary p-5 rounded-2xl border-2 border-border shadow-sm flex items-center gap-2 transition-colors hover:border-blue-500/30'>
              <span className='text-[10px] uppercase text-slate-500 dark:text-slate-400 tracking-[0.2em] font-black'>
                SENSEX
              </span>
              <div className='flex gap-4 items-center'>
                <span className='text-2xl font-black text-text tracking-tighter'>
                  {sensex.close?.toLocaleString('en-IN')}
                </span>
                <span
                  className={`text-xs font-black px-2 py-0.5 rounded-full w-fit mt-1 ${isSensexUp ? 'bg-green-500 text-white shadow-lg shadow-green-500/20' : 'bg-red-500 text-white shadow-lg shadow-red-500/20'}`}
                >
                  {isSensexUp ? '▲' : '▼'}{' '}
                  {Math.abs(sensex.change_pct)?.toFixed(2)}%
                </span>
              </div>
            </div>
          </div>

          <HighConvictionDigest />

          <ChangeBanner
            changes={changesData?.changes || []}
            asOf={changesData?.as_of}
            prevDate={changesData?.prev_date}
            loading={changesLoading}
          />

          {!isMobile ? (
            <div className='p-6 bg-bg-secondary border-2 border-border rounded-2xl shadow-sm'>
              <div className='flex flex-wrap gap-10 items-start'>
                <div className='flex flex-col gap-4'>
                  <div className='flex items-center gap-2'>
                    <Filter size={18} className='text-blue-500' />
                    <h3 className='text-[11px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400'>
                      Confluence
                    </h3>
                  </div>
                  <div className='flex flex-row gap-2.5'>
                    {map(
                      (c) => (
                        <label
                          key={c}
                          className={`flex items-center gap-2 py-2 px-4 rounded-xl text-xs font-black uppercase tracking-wider cursor-pointer transition-all border-2 shadow-sm ${confluenceFilter === c ? 'bg-blue-600 text-white border-blue-600 shadow-blue-500/30' : 'bg-slate-50 dark:bg-slate-900/50 text-slate-500 border-transparent hover:border-slate-200 dark:hover:border-slate-800'}`}
                        >
                          <input
                            type='radio'
                            name='confluence'
                            value={c}
                            checked={confluenceFilter === c}
                            onChange={(e) =>
                              setConfluenceFilter(e.target.value)
                            }
                            className='hidden'
                          />
                          {c === 'all'
                            ? 'All Stocks'
                            : c === 'watchlist'
                              ? `Watchlist (${count})`
                              : c === '3'
                                ? '3/3 Only'
                                : '2/3+'}
                        </label>
                      ),
                      ['all', 'watchlist', '3', '2+']
                    )}
                  </div>
                </div>

                <div className='flex flex-col gap-4 flex-1 min-w-[300px]'>
                  <div className='flex items-center justify-between'>
                    <h3 className='text-[11px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400'>
                      Sectors Selection
                    </h3>
                    <span className='text-[10px] bg-blue-500 text-white py-0.5 px-2 rounded-full font-black shadow-sm'>
                      {size(availableSectors)} AVAILABLE
                    </span>
                  </div>
                  <div className='flex flex-row flex-wrap gap-2 max-h-[240px] overflow-y-auto pr-2'>
                    {map(
                      (sector) => (
                        <label
                          key={sector}
                          className={`flex items-center gap-2.5 py-1.5 px-3.5 rounded-full text-[11px] font-bold uppercase tracking-tight cursor-pointer transition-all border-2 ${selectedSectors.includes(sector) ? 'bg-green-500 text-white border-green-500 shadow-lg shadow-green-500/20' : 'bg-slate-50 dark:bg-slate-900/50 text-slate-500 border-transparent hover:border-slate-200 dark:hover:border-slate-800'}`}
                        >
                          <input
                            type='checkbox'
                            checked={selectedSectors.includes(sector)}
                            onChange={() => toggleSector(sector)}
                            className='hidden'
                          />
                          <span>{sector}</span>
                        </label>
                      ),
                      availableSectors
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <div className='flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4'>
            <h2 className='text-3xl font-black m-0 tracking-tighter text-text uppercase'>
              Live Market Control
            </h2>
            <div className='flex gap-3 w-full sm:w-auto flex-wrap sm:flex-nowrap'>
              <button
                className='bg-slate-100 dark:bg-slate-800 border-2 border-border py-2 px-5 rounded-xl font-black text-[10px] uppercase tracking-widest flex items-center gap-2 cursor-pointer text-text transition-all hover:border-blue-500 disabled:opacity-50 shadow-sm'
                onClick={() => handleRunPipeline(50)}
                disabled={isBusy}
              >
                {isBusy && status !== 'running' ? (
                  <RefreshCcw size={16} className='animate-spin' />
                ) : (
                  <Play size={16} />
                )}
                RAPID TEST (50)
              </button>

              {isMobile ? (
                <button
                  className={`flex items-center gap-2 bg-bg-secondary border-2 border-border py-2 px-5 rounded-xl font-black text-[10px] uppercase tracking-widest text-text cursor-pointer relative transition-all shadow-sm ${confluenceFilter !== 'all' || selectedSectors.length > 0 ? 'border-blue-600 text-blue-600 bg-blue-50 dark:bg-blue-900/20' : 'hover:border-blue-500'}`}
                  onClick={() => setIsFilterSheetOpen(true)}
                >
                  <Filter size={18} />
                  <span>Filters</span>
                  {confluenceFilter !== 'all' || selectedSectors.length > 0 ? (
                    <span className='absolute -top-1 -right-1 w-3 h-3 bg-blue-600 rounded-full border-2 border-white dark:border-slate-900' />
                  ) : null}
                </button>
              ) : null}

              {!isMobile ? (
                <div className='flex items-center gap-1 bg-slate-100 dark:bg-slate-900 p-1 rounded-xl border-2 border-border shadow-inner'>
                  <button
                    className={`p-2 rounded-lg cursor-pointer flex transition-all ${viewMode === 'table' ? 'bg-blue-600 text-white shadow-md' : 'text-slate-500 hover:text-text'}`}
                    onClick={() => setViewMode('table')}
                    title='Table View'
                  >
                    <List size={18} />
                  </button>
                  <button
                    className={`p-2 rounded-lg cursor-pointer flex transition-all ${viewMode === 'grid' ? 'bg-blue-600 text-white shadow-md' : 'text-slate-500 hover:text-text'}`}
                    onClick={() => setViewMode('grid')}
                    title='Grid View'
                  >
                    <LayoutGrid size={20} />
                  </button>
                </div>
              ) : null}

              <div className='flex items-center gap-2 flex-1 sm:flex-none justify-center'>
                <ArrowUpDown size={16} className='text-text-muted' />
                <Select
                  value={sortBy}
                  onChange={setSortBy}
                  options={[
                    { value: 'confluence', label: 'Confluence' },
                    { value: 'score', label: 'Daily Score' },
                    { value: 'rsi', label: 'Low RSI' },
                  ]}
                  className='w-full sm:w-[150px]'
                />
              </div>
            </div>
          </div>
        </header>

        {size(stocks) > 0 ? (
          viewMode === 'grid' ? (
            <div className='grid grid-cols-1 sm:grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-4 sm:gap-6'>
              {map(
                (stock) => (
                  <StockCard
                    key={stock.symbol}
                    stock={stock}
                    isWatched={isWatched(stock.symbol)}
                    onToggleWatch={() => handleToggleWatchlist(stock)}
                  />
                ),
                stocks
              )}
            </div>
          ) : (
            <DataTable
              columns={columns}
              data={stocks}
              initialSort={DEFAULT_SORT}
              loading={loading && size(stocks) === 0}
            />
          )
        ) : (
          !loading && (
            <div className='flex flex-col items-center justify-center py-20 text-center text-text-muted'>
              <Filter size={48} />
              <h3 className='text-text my-4 text-lg font-bold'>
                No stocks match filters
              </h3>
              <p>Try adjusting your confluence or sector selections.</p>
              <button
                onClick={resetFilters}
                className='bg-slate-100 dark:bg-slate-800 text-blue-600 dark:text-blue-400 font-black uppercase tracking-widest text-[10px] py-2 px-4 rounded-xl border-2 border-transparent hover:border-blue-500 cursor-pointer mt-4 transition-all'
              >
                Reset Selection
              </button>
            </div>
          )
        )}

        {/* Sentinel and Footer UI */}
        {loading && size(stocks) > 0 ? (
          <div className='flex flex-col justify-center items-center gap-4 py-12 text-slate-500 animate-pulse bg-slate-50 dark:bg-slate-900/50 rounded-2xl border-2 border-border border-dashed mt-8'>
            <RefreshCcw size={32} className='animate-spin text-blue-500' />
            <span className='text-[10px] font-black uppercase tracking-[0.2em]'>
              Synchronizing Deep Market Data...
            </span>
          </div>
        ) : null}
        {!hasMore && size(stocks) > 0 ? (
          <div className='text-center py-5 text-text-muted'>
            <p>No more stocks to show</p>
          </div>
        ) : null}
        <div ref={sentinelRef} className='h-5 my-5' />
      </main>

      <FilterBottomSheet
        isOpen={isFilterSheetOpen}
        onClose={() => setIsFilterSheetOpen(false)}
        confluenceFilter={confluenceFilter}
        setConfluenceFilter={setConfluenceFilter}
        availableSectors={availableSectors}
        selectedSectors={selectedSectors}
        toggleSector={toggleSector}
        resetFilters={resetFilters}
        watchlistCount={count}
      />
    </div>
  );
};

export default Dashboard;
