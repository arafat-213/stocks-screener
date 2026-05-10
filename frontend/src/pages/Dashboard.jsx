import { useState, useEffect, useMemo } from 'react';
import { Play, Filter, ArrowUpDown, AlertCircle, LayoutGrid, List, Square, RefreshCcw, Clock } from 'lucide-react';
import { Link } from 'react-router-dom';
import { fetchResults } from '../api/client';
import { useFetch } from '../hooks/useFetch';
import { usePipeline } from '../hooks/usePipeline';
import StockCard from '../components/StockCard';
import StockCardSkeleton from '../components/StockCardSkeleton';
import FilterBottomSheet from '../components/FilterBottomSheet';
import Select from '../components/ui/Select';
import { DataTable } from '../components/ui/DataTable';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import './Dashboard.css';

const Dashboard = () => {
  // Data Fetching Hooks
  const { 
    data: stocks, 
    loading: stocksLoading, 
    error: stocksError, 
    refetch: refetchStocks 
  } = useFetch(fetchResults);

  const { 
    status, 
    stats: pipeline, 
    isBusy, 
    run: handleRunPipeline, 
    stop: handleStopPipeline, 
    error: pipelineError 
  } = usePipeline();
  
  // Filters and Sort State
  const [confluenceFilter, setConfluenceFilter] = useState('all'); // 'all', '3', '2+'
  const [selectedSectors, setSelectedSectors] = useState([]);
  const [sortBy, setSortBy] = useState('confluence'); // 'confluence', 'score', 'rsi', 'pe'
  const [viewMode, setViewMode] = useState('table'); // 'grid', 'table'

  // Responsiveness State
  const [isFilterSheetOpen, setIsFilterSheetOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

  // Implement refresh side-effect: when status transitions from running to complete, call refetchStocks()
  const [prevStatus, setPrevStatus] = useState(status);
  useEffect(() => {
    if (prevStatus === 'running' && status === 'complete') {
      refetchStocks();
    }
    setPrevStatus(status);
  }, [status, prevStatus, refetchStocks]);

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
    if (!stocks) return [];
    const sectors = new Set(stocks.map(s => s.sector).filter(Boolean));
    return Array.from(sectors).sort();
  }, [stocks]);

  // Client-side Filtering
  const filteredStocks = useMemo(() => {
    if (!stocks) return [];
    return stocks
      .filter(stock => {
        // Confluence Filter
        if (confluenceFilter === '3') return stock.confluence_count === 3;
        if (confluenceFilter === '2+') return stock.confluence_count >= 2;
        return true;
      })
      .filter(stock => {
        // Sector Filter
        if (selectedSectors.length === 0) return true;
        return selectedSectors.includes(stock.sector);
      });
  }, [stocks, confluenceFilter, selectedSectors]);

  // Column Definitions for DataTable
  const columns = [
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

  if (stocksLoading && !stocks) {
    return (
      <div className="dashboard-page">
        <main className="dashboard-content">
          <div className="summary-bar">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="summary-item">
                <div className="skeleton-line" className="skeleton-h-40"></div>
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

  const market = pipeline?.market_context || [];
  const nifty = market.find(m => m.symbol === '^NSEI') || {};
  const sensex = market.find(m => m.symbol === '^BSESN') || {};
  
  const isNiftyUp = nifty.change_pct >= 0;
  const isSensexUp = sensex.change_pct >= 0;

  return (
    <div className="dashboard-page">
      {(stocksError || pipelineError) && (
        <ErrorBanner message={stocksError || pipelineError} />
      )}

      {/* Main Content */}
      <main className="dashboard-content">
        <header className="dashboard-header">
          <div className="summary-bar">
            {status === 'running' && (
              <div className="summary-item status-badge running">
                <div className="flex-center-gap-12">
                  <RefreshCcw size={16} className="spin" />
                  <div>
                    <span className="label">Pipeline Running</span>
                    <span className="value" className="fs-12">
                      {pipeline?.stocks_fetched || 0} fetched | {pipeline?.stocks_scored || 0} scored
                    </span>
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
                <small>({isNiftyUp ? '▲' : '▼'} {Math.abs(nifty.change_pct)?.toFixed(2)}%)</small>
              </span>
            </div>
            <div className="summary-item">
              <div className="flex-center-gap-8">
                <Clock size={16} className="text-muted" />
                <div>
                  <span className="label">Last Updated</span>
                  <span className="value" className="fs-14">
                    {pipeline?.scored_at ? new Date(pipeline.scored_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Never'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {!isMobile && (
            <div className="filters-container card">
              <div className="filter-flex-wrap">
                <div className="filter-group">
                  <div className="filter-header" className="mb-12">
                    <Filter size={16} className="mr-8 inline" />
                    <h3 className="inline fs-14">Confluence</h3>
                  </div>
                  <div className="radio-group" className="flex-row-gap-8">
                    {['all', '3', '2+'].map(c => (
                      <label key={c} className={`radio-label ${confluenceFilter === c ? 'active' : ''}`} className="radio-label">
                        <input 
                          type="radio" 
                          name="confluence" 
                          value={c} 
                          checked={confluenceFilter === c}
                          onChange={(e) => setConfluenceFilter(e.target.value)}
                        />
                        {c === 'all' ? 'All Stocks' : c === '3' ? '3/3 Only' : '2/3+'}
                      </label>
                    ))}
                  </div>
                </div>

                <div className="filter-group sectors flex-1-min-300">
                  <div className="filter-header" className="mb-12">
                    <h3 className="fs-14">Sectors <span className="count" className="ml-8">{availableSectors.length}</span></h3>
                  </div>
                  <div className="checkbox-list flex-row-wrap-gap-8">
                    {availableSectors.map(sector => (
                      <label key={sector} className={`checkbox-label ${selectedSectors.includes(sector) ? 'active' : ''}`}>
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
                  {(confluenceFilter !== 'all' || selectedSectors.length > 0) && <span className="indicator" />}
                </button>
              )}
              
              {!isMobile && (
                <div className="view-toggle view-toggle-container">
                  <button 
                    className={`toggle-btn ${viewMode === 'table' ? 'active' : ''}`}
                    onClick={() => setViewMode('table')}
                    title="Table View"
                    style={{ background: 'none', border: 'none', padding: '4px', cursor: 'pointer', display: 'flex', color: viewMode === 'table' ? 'var(--color-bullish)' : 'inherit' }}
                  >
                    <List size={20} />
                  </button>
                  <button 
                    className={`toggle-btn ${viewMode === 'grid' ? 'active' : ''}`}
                    onClick={() => setViewMode('grid')}
                    title="Grid View"
                    style={{ background: 'none', border: 'none', padding: '4px', cursor: 'pointer', display: 'flex', color: viewMode === 'grid' ? 'var(--color-bullish)' : 'inherit' }}
                  >
                    <LayoutGrid size={20} />
                  </button>
                </div>
              )}

              <div className="sort-controls-wrapper" className="flex-center-gap-8">
                <ArrowUpDown size={16} className="text-muted" />
                <Select
                  value={sortBy}
                  onChange={setSortBy}
                  options={[
                    { value: 'confluence', label: 'Confluence' },
                    { value: 'score', label: 'Daily Score' },
                    { value: 'rsi', label: 'Low RSI' },
                    { value: 'pe', label: 'Value (P/E)' }
                  ]}
                  className="sort-select"
                />
              </div>
            </div>
          </div>
        </header>

        {filteredStocks.length > 0 ? (
          viewMode === 'grid' ? (
            <div className="stock-grid">
              {filteredStocks.map(stock => (
                <StockCard key={stock.symbol} stock={stock} />
              ))}
            </div>
          ) : (
            <DataTable 
              columns={columns} 
              data={filteredStocks} 
              initialSort={{ key: 'score', direction: 'desc' }}
              loading={stocksLoading}
            />
          )
        ) : (
          <div className="no-results">
            <Filter size={48} />
            <h3>No stocks match filters</h3>
            <p>Try adjusting your confluence or sector selections.</p>
            <button onClick={resetFilters} className="text-button">Reset All Filters</button>
          </div>
        )}
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
      />
    </div>
  );
};

export default Dashboard;
