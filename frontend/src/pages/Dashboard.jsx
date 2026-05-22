import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Play, Filter, ArrowUpDown, AlertCircle, LayoutGrid, List, Square, RefreshCcw } from 'lucide-react';
import { Link } from 'react-router-dom';
import { fetchResults, getDashboardChanges } from '../api/client';
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

const Dashboard = () => {
  // Data Fetching Hooks
  const [stocks, setStocks] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const { data: changesData, loading: changesLoading, refetch: refetchChanges } = useFetch(getDashboardChanges);

  const { 
    status, 
    stats: pipeline, 
    isBusy, 
    run: handleRunPipeline, 
    stop: handleStopPipeline, 
    error: pipelineError 
  } = usePipeline();
  
  const { market_context, error: marketError } = useMarketData();
  const { watchlist, toggle, isWatched, count } = useWatchlist();
  
  // Filters and Sort State
  const [confluenceFilter, setConfluenceFilter] = useState('all'); // 'all', 'watchlist', '3', '2+'
  const [selectedSectors, setSelectedSectors] = useState([]);
  const [sortBy, setSortBy] = useState('confluence'); // 'confluence', 'score', 'rsi', 'pe'
  const [viewMode, setViewMode] = useState('table'); // 'grid', 'table'

  // Responsiveness State
  const [isFilterSheetOpen, setIsFilterSheetOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

  const loadMore = useCallback(async (isReset = false) => {
    if (loading || (!hasMore && !isReset)) return;

    setLoading(true);
    const currentOffset = isReset ? 0 : offset;
    
    try {
      const data = await fetchResults({
        offset: currentOffset,
        limit: 50,
        sector: selectedSectors.join(','),
        confluence: confluenceFilter === 'watchlist' ? undefined : confluenceFilter,
        symbols: confluenceFilter === 'watchlist' ? [...watchlist].join(',') : undefined,
        sort_by: sortBy
      });

      if (isReset) {
        setStocks(data.items);
        setOffset(50);
      } else {
        setStocks(prev => [...prev, ...data.items]);
        setOffset(currentOffset + 50);
      }

      setHasMore(data.has_more);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to fetch stocks');
    } finally {
      setLoading(false);
    }
  }, [offset, hasMore, loading, selectedSectors, confluenceFilter, sortBy, watchlist]);

  // Infinite Scroll Trigger
  const sentinelRef = useRef(null);
  useEffect(() => {
    const obs = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore && !loading) {
        loadMore();
      }
    }, { threshold: 0.1 });

    if (sentinelRef.current) obs.observe(sentinelRef.current);
    return () => obs.disconnect();
  }, [hasMore, loading, loadMore]);

  // Filter/Sort Integration
  useEffect(() => {
    loadMore(true);
  }, [selectedSectors, confluenceFilter, sortBy]);

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

  // Derived: Available Sectors (only from current stocks)
  const availableSectors = useMemo(() => {
    if (!stocks || stocks.length === 0) return [];
    const sectors = new Set(stocks.map(s => s.sector).filter(Boolean));
    return Array.from(sectors).sort();
  }, [stocks]);

  // Column Definitions for DataTable
  const columns = [
    {
      key: 'watchlist',
      label: '★',
      sortable: false,
      render: (_, row) => (
        <WatchlistStar 
          symbol={row.symbol} 
          isWatched={isWatched(row.symbol)} 
          onToggle={toggle} 
        />
      )
    },
    { 
      key: 'symbol', 
      label: 'Symbol', 
      sortable: true,
      render: (val) => (
        <Link to={`/stocks/${val}`} className="text-bullish font-bold no-underline hover:underline">
          {val.replace('.NS', '')}
        </Link>
      )
    },
    { 
      key: 'setup', 
      label: 'Setup', 
      sortable: true,
      accessor: (row) => row.setup?.setup_type || '',
      render: (_, row) => <SetupBadge setup={row.setup} />
    },
    { 
      key: 'close_price', 
      label: 'Price', 
      sortable: true,
      render: (val) => `₹${val?.toLocaleString('en-IN', { minimumFractionDigits: 1 })}`
    },
    { 
      key: 'price_change_pct', 
      label: 'Change %', 
      sortable: true,
      render: (val) => (
        <span className={val >= 0 ? 'text-bullish' : 'text-bearish'}>
          {val >= 0 ? '+' : ''}{val?.toFixed(2)}%
        </span>
      )
    },
    { 
      key: 'score', 
      label: 'Score', 
      sortable: true,
      accessor: (row) => row.timeframes?.D?.score || 0,
      render: (val) => <span className="font-bold">{val || '-'}</span>
    },
    { 
      key: 'rs_score', 
      label: 'RS', 
      sortable: true,
      accessor: (row) => row.timeframes?.D?.rs_score || 0,
      render: (val) => <span className="text-primary font-bold">{val?.toFixed(0) || '-'}</span>
    },
    { 
      key: 'adx', 
      label: 'ADX', 
      sortable: true,
      accessor: (row) => row.timeframes?.D?.adx || 0,
      render: (val) => val?.toFixed(1) || '-'
    },
    { 
      key: 'roe', 
      label: 'ROE %', 
      sortable: true,
      accessor: (row) => row.fundamentals?.roe || 0,
      render: (val) => `${val?.toFixed(1) || '-'}%`
    },
    { 
      key: 'pe', 
      label: 'P/E', 
      sortable: true,
      accessor: (row) => row.fundamentals?.pe || 999,
      render: (val) => val?.toFixed(1) || '-'
    },
    { 
      key: 'sector', 
      label: 'Sector', 
      sortable: true 
    }
  ];

  const toggleSector = (sector) => {
    setSelectedSectors(prev => 
      prev.includes(sector) ? prev.filter(s => s !== sector) : [...prev, sector]
    );
  };

  const resetFilters = () => {
    setConfluenceFilter('all');
    setSelectedSectors([]);
  };

  const hasData = stocks.length > 0;

  if (loading && !hasData) {
    return (
      <div className="w-full">
        <main className="flex-1">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="bg-bg-secondary p-4 rounded-xl border border-border flex flex-col gap-1">
                <div className="h-10 w-full bg-bg-elevated rounded-md animate-pulse"></div>
              </div>
            ))}
          </div>
          <div className="mt-8">
            {viewMode === 'grid' ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {[1, 2, 3, 4, 5, 6].map(i => <StockCardSkeleton key={i} />)}
              </div>
            ) : (
              <div className="bg-bg-secondary rounded-xl border border-border mt-4 overflow-hidden">
                <div className="flex bg-bg-elevated border-bottom border-border min-w-fit">
                  {columns.map(col => (
                    <div key={col.key} className="px-4 py-3 text-[11px] font-bold text-text-muted uppercase tracking-wider flex items-center gap-2 flex-1 min-w-[120px]">
                      {col.label}
                    </div>
                  ))}
                </div>
                {Array.from({ length: 10 }).map((_, i) => (
                  <div key={i} className="flex border-b border-border transition-colors hover:bg-bg-elevated">
                    {columns.map(col => (
                      <div key={col.key} className="p-4 text-sm text-text flex-1 min-w-[120px] flex items-center">
                        <div className="h-4 w-full bg-bg-elevated rounded-sm animate-pulse" />
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        </main>
      </div>
    );
  }

  if (pipeline?.status === 'never_run') {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center text-text-muted">
        <AlertCircle size={64} />
        <h1 className="text-text my-4 text-2xl font-bold">No Data Available</h1>
        <p>The pipeline hasn't been run yet. Start it to see market analysis.</p>
        <button 
          className="mt-6 bg-bullish text-white border-none py-3 px-6 rounded-lg font-bold flex items-center gap-2 cursor-pointer transition-opacity hover:opacity-90" 
          onClick={() => handleRunPipeline()} 
          disabled={isBusy}
        >
          <Play size={20} /> Run Initial Pipeline
        </button>
      </div>
    );
  }

  const market = market_context || [];
  const nifty = market.find(m => m.symbol === '^NSEI') || {};
  const sensex = market.find(m => m.symbol === '^BSESN') || {};

  const isNiftyUp = nifty.change_pct >= 0;
  const isSensexUp = sensex.change_pct >= 0;

  const hasMarketData = market.length > 0;

  return (
    <div className="w-full animate-fade-in">
      {(error || pipelineError || marketError) && (
        <ErrorBanner message={error || pipelineError || marketError} />
      )}

      {pipeline?.is_stale && (
        <StaleBanner
          lastUpdated={pipeline.scored_at}
          dataAgeHours={pipeline.data_age_hours}
          onRunPipeline={handleRunPipeline}
          isBusy={isBusy}
        />
      )}

      {!hasMarketData && !loading && (
        <div className="bg-bg-secondary p-4 mb-4 rounded-lg border border-border text-text-muted">
          Market data is currently unavailable.
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1">
        <header className="mb-8 flex flex-col gap-6">
          <div className="flex justify-between items-center">
            <GlobalSearch />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {status === 'running' && (
              <div className="bg-bullish/5 border-bullish p-4 rounded-xl border flex flex-row justify-between items-center gap-3">
                <div className="flex items-center gap-3 w-full">
                  <RefreshCcw size={16} className="animate-spin text-bullish shrink-0" />
                  <div className="flex-1 overflow-hidden">
                    <span className="text-[11px] uppercase text-text-muted tracking-wider font-semibold block">Pipeline Running</span>
                    <span className="text-xl font-extrabold text-text text-[12px] block mb-1">
                      {pipeline?.stocks_fetched || 0} fetched |{' '}
                      {pipeline?.stocks_scored || 0} scored
                    </span>
                    <PipelineProgress
                      fetched={pipeline?.stocks_fetched || 0}
                      scored={pipeline?.stocks_scored || 0}
                      total={pipeline?.total_symbols || 0}
                      tier1Count={pipeline?.tier1_count || 0}
                    />
                  </div>
                  <button
                    className="bg-bearish text-white border-none py-1.5 px-2.5 rounded-md text-[11px] font-bold flex items-center gap-1.5 cursor-pointer transition-opacity hover:opacity-90 disabled:bg-text-muted disabled:cursor-not-allowed ml-auto shrink-0"
                    onClick={handleStopPipeline}
                    disabled={status === 'stopping'}
                    title="Stop Pipeline"
                  >
                    <Square size={14} fill="currentColor" />
                    {status === 'stopping' ? 'Stopping...' : 'Stop'}
                  </button>
                </div>
              </div>
            )}
            <div className="bg-bg-secondary p-4 rounded-xl border border-border flex flex-col gap-1">
              <span className="text-[11px] uppercase text-text-muted tracking-wider font-semibold">Total Scored</span>
              <span className="text-xl font-extrabold text-text">{stocks?.length || 0}</span>
            </div>
            <div className="bg-bg-secondary p-4 rounded-xl border border-border flex flex-col gap-1">
              <span className="text-[11px] uppercase text-text-muted tracking-wider font-semibold">Nifty 50</span>
              <span className={`text-xl font-extrabold ${isNiftyUp ? 'text-bullish' : 'text-bearish'}`}>
                {nifty.close?.toLocaleString('en-IN')}
                <small className="text-[12px] font-semibold ml-1">
                  ({isNiftyUp ? '▲' : '▼'}{' '}
                  {Math.abs(nifty.change_pct)?.toFixed(2)}%)
                </small>
              </span>
            </div>
            <div className="bg-bg-secondary p-4 rounded-xl border border-border flex flex-col gap-1">
              <span className="text-[11px] uppercase text-text-muted tracking-wider font-semibold">SENSEX</span>
              <span className={`text-xl font-extrabold ${isSensexUp ? 'text-bullish' : 'text-bearish'}`}>
                {sensex.close?.toLocaleString('en-IN')}
                <small className="text-[12px] font-semibold ml-1">
                  ({isSensexUp ? '▲' : '▼'}{' '}
                  {Math.abs(sensex.change_pct)?.toFixed(2)}%)
                </small>
              </span>
            </div>
          </div>

          <ChangeBanner
            changes={changesData?.changes || []}
            asOf={changesData?.as_of}
            prevDate={changesData?.prev_date}
            loading={changesLoading}
          />

          {!isMobile && (
            <div className="p-5 bg-bg-secondary border border-border rounded-lg shadow-sm">
              <div className="flex flex-wrap gap-8 items-start">
                <div className="flex flex-col gap-3">
                  <div className="mb-1 flex items-center">
                    <Filter size={16} className="mr-2 inline" />
                    <h3 className="inline text-sm font-bold">Confluence</h3>
                  </div>
                  <div className="flex flex-row gap-2">
                    {['all', 'watchlist', '3', '2+'].map((c) => (
                      <label
                        key={c}
                        className={`flex items-center gap-2 py-2 px-3 rounded-lg text-sm cursor-pointer transition-all border border-border bg-bg-secondary text-text hover:bg-bg-elevated ${confluenceFilter === c ? 'bg-bullish/10 text-bullish font-semibold border-bullish' : ''}`}
                      >
                        <input
                          type="radio"
                          name="confluence"
                          value={c}
                          checked={confluenceFilter === c}
                          onChange={(e) => setConfluenceFilter(e.target.value)}
                          className="hidden"
                        />
                        {c === 'all'
                          ? 'All Stocks'
                          : c === 'watchlist'
                            ? `Watchlist (${count})`
                            : c === '3'
                              ? '3/3 Only'
                              : '2/3+'}
                      </label>
                    ))}
                  </div>
                </div>

                <div className="flex flex-col gap-3 flex-1 min-w-[300px]">
                  <div className="mb-1">
                    <h3 className="text-sm font-bold">
                      Sectors{' '}
                      <span className="text-[11px] bg-bg-elevated py-0.5 px-1.5 rounded text-text-muted ml-2">
                        {availableSectors.length}
                      </span>
                    </h3>
                  </div>
                  <div className="flex flex-row flex-wrap gap-2 max-h-[240px] overflow-y-auto pr-1">
                    {availableSectors.map((sector) => (
                      <label
                        key={sector}
                        className={`flex items-center gap-2.5 py-1 px-3 rounded-full text-[12px] cursor-pointer text-text border border-border bg-bg-secondary transition-all hover:bg-bg-elevated ${selectedSectors.includes(sector) ? 'bg-bullish/10 text-bullish font-semibold border-bullish' : ''}`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedSectors.includes(sector)}
                          onChange={() => toggleSector(sector)}
                          className="hidden"
                        />
                        <span>{sector}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <h2 className="text-2xl font-extrabold m-0 tracking-tight text-text">Market Screener</h2>
            <div className="flex gap-3 w-full sm:w-auto flex-wrap sm:flex-nowrap">
              <button
                className="bg-bg-elevated border border-border py-2 px-4 rounded-lg font-semibold flex items-center gap-2 cursor-pointer text-text transition-all hover:not-disabled:border-text-muted disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={() => handleRunPipeline(50)}
                disabled={isBusy}
              >
                <Play size={16} /> Test (50)
              </button>

              {isMobile && (
                <button
                  className={`flex items-center gap-2 bg-bg-secondary border border-border py-2 px-4 rounded-[10px] font-semibold text-text cursor-pointer relative transition-all ${confluenceFilter !== 'all' || selectedSectors.length > 0 ? 'border-bullish text-bullish bg-bullish/5' : ''}`}
                  onClick={() => setIsFilterSheetOpen(true)}
                >
                  <Filter size={20} />
                  <span>Filters</span>
                  {(confluenceFilter !== 'all' ||
                    selectedSectors.length > 0) && (
                    <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-bullish rounded-full border-2 border-bg-secondary" />
                  )}
                </button>
              )}

              {!isMobile && (
                <div className="flex items-center gap-1 bg-bg-secondary p-1 rounded-md border border-border">
                  <button
                    className={`p-1 rounded cursor-pointer flex transition-colors ${viewMode === 'table' ? 'text-bullish bg-bg-elevated' : 'text-text-muted hover:text-text'}`}
                    onClick={() => setViewMode('table')}
                    title="Table View"
                  >
                    <List size={20} />
                  </button>
                  <button
                    className={`p-1 rounded cursor-pointer flex transition-colors ${viewMode === 'grid' ? 'text-bullish bg-bg-elevated' : 'text-text-muted hover:text-text'}`}
                    onClick={() => setViewMode('grid')}
                    title="Grid View"
                  >
                    <LayoutGrid size={20} />
                  </button>
                </div>
              )}

              <div className="flex items-center gap-2 flex-1 sm:flex-none justify-center">
                <ArrowUpDown size={16} className="text-text-muted" />
                <Select
                  value={sortBy}
                  onChange={setSortBy}
                  options={[
                    { value: 'confluence', label: 'Confluence' },
                    { value: 'score', label: 'Daily Score' },
                    { value: 'rsi', label: 'Low RSI' },
                    { value: 'pe', label: 'Value (P/E)' },
                  ]}
                  className="w-full sm:w-[150px]"
                />
              </div>
            </div>
          </div>
        </header>

        {stocks.length > 0 ? (
          viewMode === 'grid' ? (
            <div className="grid grid-cols-1 sm:grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-6">
              {stocks.map((stock) => (
                <StockCard
                  key={stock.symbol}
                  stock={stock}
                  isWatched={isWatched(stock.symbol)}
                  onToggleWatch={toggle}
                />
              ))}
            </div>
          ) : (
            <DataTable
              columns={columns}
              data={stocks}
              initialSort={{ key: 'score', direction: 'desc' }}
              loading={loading && stocks.length === 0}
            />
          )
        ) : (
          !loading && (
            <div className="flex flex-col items-center justify-center py-20 text-center text-text-muted">
              <Filter size={48} />
              <h3 className="text-text my-4 text-lg font-bold">No stocks match filters</h3>
              <p>Try adjusting your confluence or sector selections.</p>
              <button onClick={resetFilters} className="bg-none border-none color-bullish font-semibold cursor-pointer mt-3 underline">
                Reset All Filters
              </button>
            </div>
          )
        )}

        {/* Sentinel and Footer UI */}
        {loading && stocks.length > 0 && (
          <div className="flex justify-center items-center gap-2 py-5 text-text-muted">
            <RefreshCcw size={20} className="animate-spin text-bullish" />
            <span>Loading more stocks...</span>
          </div>
        )}
        {!hasMore && stocks.length > 0 && (
          <div className="text-center py-5 text-text-muted">
            <p>No more stocks to show</p>
          </div>
        )}
        <div ref={sentinelRef} className="h-5 my-5" />
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
