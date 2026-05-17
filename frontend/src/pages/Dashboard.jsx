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
import './Dashboard.css';

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
        <Link to={`/stocks/${val}`} className="table-link">
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
        <span className={val >= 0 ? 'text-positive' : 'text-negative'}>
          {val >= 0 ? '+' : ''}{val?.toFixed(2)}%
        </span>
      )
    },
    { 
      key: 'score', 
      label: 'Score', 
      sortable: true,
      accessor: (row) => row.timeframes?.D?.score || 0,
      render: (val) => <span className="bold">{val || '-'}</span>
    },
    { 
      key: 'rs_score', 
      label: 'RS', 
      sortable: true,
      accessor: (row) => row.timeframes?.D?.rs_score || 0,
      render: (val) => <span className="text-primary bold">{val?.toFixed(0) || '-'}</span>
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
      <div className="dashboard-page">
        <main className="dashboard-content">
          <div className="summary-bar">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="summary-item">
                <div className="skeleton-line skeleton-h-40"></div>
              </div>
            ))}
          </div>
          <div className="mt-32">
            {viewMode === 'grid' ? (
              <div className="stock-grid">
                {[1, 2, 3, 4, 5, 6].map(i => <StockCardSkeleton key={i} />)}
              </div>
            ) : (
              <div className="data-table-container skeleton">
                <div className="table-header">
                  {columns.map(col => <div key={col.key} className="header-cell">{col.label}</div>)}
                </div>
                {Array.from({ length: 10 }).map((_, i) => (
                  <div key={i} className="table-row">
                    {columns.map(col => <div key={col.key} className="table-cell"><div className="skeleton-line" /></div>)}
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
      <div className="empty-state">
        <AlertCircle size={64} />
        <h1>No Data Available</h1>
        <p>The pipeline hasn't been run yet. Start it to see market analysis.</p>
        <button className="primary-button" onClick={() => handleRunPipeline()} disabled={isBusy}>
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
    <div className="dashboard-page">
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
        <div className="info-banner">Market data is currently unavailable.</div>
      )}

      {/* Main Content */}
      <main className="dashboard-content">
        <header className="dashboard-header">
          <div className="flex justify-between items-center mb-6">
            <GlobalSearch />
          </div>

          <div className="summary-bar">
            {status === 'running' && (
              <div className="summary-item status-badge running">
                <div className="flex-center-gap-12">
                  <RefreshCcw size={16} className="spin" />
                  <div style={{ flex: 1 }}>
                    <span className="label">Pipeline Running</span>
                    <span
                      className="value fs-12"
                      style={{ display: 'block', marginBottom: '4px' }}
                    >
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
                    className="stop-button"
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
            <div className="summary-item">
              <span className="label">Total Scored</span>
              <span className="value">{stocks?.length || 0}</span>
            </div>
            <div className="summary-item market">
              <span className="label">Nifty 50</span>
              <span className={`value ${isNiftyUp ? 'success' : 'danger'}`}>
                {nifty.close?.toLocaleString('en-IN')}
                <small>
                  ({isNiftyUp ? '▲' : '▼'}{' '}
                  {Math.abs(nifty.change_pct)?.toFixed(2)}%)
                </small>
              </span>
            </div>
            <div className="summary-item market">
              <span className="label">SENSEX</span>
              <span className={`value ${isSensexUp ? 'success' : 'danger'}`}>
                {sensex.close?.toLocaleString('en-IN')}
                <small>
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
            <div className="filters-container card">
              <div className="filter-flex-wrap">
                <div className="filter-group">
                  <div className="mb-12">
                    <Filter size={16} className="mr-8 inline" />
                    <h3 className="inline fs-14">Confluence</h3>
                  </div>
                  <div className="flex-row-gap-8">
                    {['all', 'watchlist', '3', '2+'].map((c) => (
                      <label
                        key={c}
                        className={`radio-label ${confluenceFilter === c ? 'active' : ''}`}
                      >
                        <input
                          type="radio"
                          name="confluence"
                          value={c}
                          checked={confluenceFilter === c}
                          onChange={(e) => setConfluenceFilter(e.target.value)}
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

                <div className="filter-group sectors flex-1-min-300">
                  <div className="mb-12">
                    <h3 className="fs-14">
                      Sectors{' '}
                      <span className="count ml-8">
                        {availableSectors.length}
                      </span>
                    </h3>
                  </div>
                  <div className="checkbox-list flex-row-wrap-gap-8">
                    {availableSectors.map((sector) => (
                      <label
                        key={sector}
                        className={`checkbox-label ${selectedSectors.includes(sector) ? 'active' : ''}`}
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

          <div className="action-bar">
            <h2>Market Screener</h2>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                className="secondary-button"
                onClick={() => handleRunPipeline(50)}
                disabled={isBusy}
              >
                <Play size={16} /> Test (50)
              </button>

              {isMobile && (
                <button
                  className={`filter-mobile-btn ${confluenceFilter !== 'all' || selectedSectors.length > 0 ? 'active' : ''}`}
                  onClick={() => setIsFilterSheetOpen(true)}
                >
                  <Filter size={20} />
                  <span>Filters</span>
                  {(confluenceFilter !== 'all' ||
                    selectedSectors.length > 0) && (
                    <span className="indicator" />
                  )}
                </button>
              )}

              {!isMobile && (
                <div className="view-toggle view-toggle-container">
                  <button
                    className={`toggle-btn ${viewMode === 'table' ? 'active' : ''}`}
                    onClick={() => setViewMode('table')}
                    title="Table View"
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: '4px',
                      cursor: 'pointer',
                      display: 'flex',
                      color:
                        viewMode === 'table'
                          ? 'var(--color-bullish)'
                          : 'inherit',
                    }}
                  >
                    <List size={20} />
                  </button>
                  <button
                    className={`toggle-btn ${viewMode === 'grid' ? 'active' : ''}`}
                    onClick={() => setViewMode('grid')}
                    title="Grid View"
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: '4px',
                      cursor: 'pointer',
                      display: 'flex',
                      color:
                        viewMode === 'grid'
                          ? 'var(--color-bullish)'
                          : 'inherit',
                    }}
                  >
                    <LayoutGrid size={20} />
                  </button>
                </div>
              )}

              <div className="flex-center-gap-8">
                <ArrowUpDown size={16} className="text-muted" />
                <Select
                  value={sortBy}
                  onChange={setSortBy}
                  options={[
                    { value: 'confluence', label: 'Confluence' },
                    { value: 'score', label: 'Daily Score' },
                    { value: 'rsi', label: 'Low RSI' },
                    { value: 'pe', label: 'Value (P/E)' },
                  ]}
                  className="sort-select"
                />
              </div>
            </div>
          </div>
        </header>

        {stocks.length > 0 ? (
          viewMode === 'grid' ? (
            <div className="stock-grid">
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
            <div className="no-results">
              <Filter size={48} />
              <h3>No stocks match filters</h3>
              <p>Try adjusting your confluence or sector selections.</p>
              <button onClick={resetFilters} className="text-button">
                Reset All Filters
              </button>
            </div>
          )
        )}

        {/* Sentinel and Footer UI */}
        {loading && stocks.length > 0 && (
          <div
            className="loading-more"
            style={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              gap: '8px',
              padding: '20px',
              color: 'var(--color-text-muted)',
            }}
          >
            <RefreshCcw size={20} className="spin" />
            <span>Loading more stocks...</span>
          </div>
        )}
        {!hasMore && stocks.length > 0 && (
          <div
            className="no-more"
            style={{
              textAlign: 'center',
              padding: '20px',
              color: 'var(--color-text-muted)',
            }}
          >
            <p>No more stocks to show</p>
          </div>
        )}
        <div ref={sentinelRef} style={{ height: '20px', margin: '20px 0' }} />
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
